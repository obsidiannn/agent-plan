from __future__ import annotations

import json
import re
import time

from openai import OpenAI

from fde_exam_gen.config import Settings
from fde_exam_gen.models import (
    BlindResult,
    GeneratedQuestionBatch,
    JudgeResult,
)

SYSTEM_PROMPT = """你是「腾讯云 FDE 课程」的命题专家。你的唯一事实来源是用户提供的《课程原文片段》。

硬性规则：
1. 只能考查原文明确陈述的内容；原文没有的信息一律不得作为题目或答案。
2. 每题只考查一个独立事实（claim），不要把多个知识点塞进一道题。
3. 单选题必须有 4 个选项，有且仅有 1 个正确答案。
4. 多选题必须有 4 个选项，正确答案为 2～3 个（不要 4 个全对），且至少有一个错误选项是常见误区。
5. 错误选项必须“合理但明确错误”：与正确答案同类别、同粒度、长度相近，模拟客户或新人常见的错误理解；不得使用“以上都对”“以上都不对”“以上均是”。
6. 题干必须自洽、无歧义，不得泄露答案，不得使用双重否定。
7. 必须给出原文中连续的证据片段 evidence_quote，长度 8～300 字，且逐字来自原文（可去掉多余空白）。
8. 必须给出 source_page：证据片段所在的 PDF 页码，只能使用原文片段中标注的页码。
9. 必须给出 claim：一句话概括本题考查的唯一规则/判断/事实，不能与题干重复，不能是“某小节属于某章”。
10. 不要考查页码、版本号、日期等无学习价值的细节，除非原文将其作为核心知识。
11. 只输出 JSON，不要输出 Markdown 代码块、解释或前后缀。

【必须遵守的出题形态】
12. 严禁目录题、章节归属题、页码题。不得出现“以下哪一项属于第 X 章/某小节”“以下哪些小节属于第 X 章”“课程目录”“位于第 X 章”“章节/小节归属”等问法；题干和选项都不能只是章节标题或小节标题。
13. 题干必须从以下真实工作情境切入：客户场景与选型、方案决策与边界判断、故障排查、流程/阶段顺序、成本/积分/数量口径、方案对比、常见误区辨析。不能只问“X 是什么/定义是什么”。
14. 单选：3 个干扰项都要有迷惑性，分别对应一种常见误解；不要用明显荒谬、与题干无关或一眼可排除的选项。
15. 多选：正确项 2～3 个；至少 1 个错误项是“听起来合理但原文明确否定”的常见误区。
16. 解析必须逐项说明：正确项为什么对，至少两个干扰项错在哪里，不能只重复题干。
17. 必须填写 style，取值只能是：
    SCENARIO（客户场景/选型/决策）、TROUBLESHOOTING（故障排查）、
    COMPARISON（方案/产品/概念对比）、PROCESS（流程/阶段/顺序）、
    CALCULATION（成本/积分/数量口径）、JUDGMENT（规则/边界/正误判断）。
18. 同一知识点不要反复出同一种问法；优先考“怎么判断、怎么选、先做什么、为什么错”，而不是“是什么”。"""


STYLE_GUIDE = {
    "SCENARIO": "客户场景/选型/决策：给一个客户或项目情境，问应该怎么判断、选哪个方案、下一步做什么。",
    "TROUBLESHOOTING": "故障排查：给一个具体故障现象，问正确的排查顺序或根因。",
    "COMPARISON": "方案对比：比较两个产品/做法/阶段的差异，问哪个更合适或差异是什么。",
    "PROCESS": "流程/阶段/顺序：问某阶段该做什么、先后顺序、何时确定某件事。",
    "CALCULATION": "成本/积分/数量口径：给一个计费或投入情境，问什么动作计费、成本怎么算。",
    "JUDGMENT": "规则/边界/正误判断：给一个说法或做法，判断是否符合原文规则。",
}

FEW_SHOT_EXAMPLES = """
【风格示例：只模仿提问方式、干扰项设计和解析方式；严禁照抄题干、选项和考点】

示例 1（SCENARIO 单选）
某客户 IT 团队希望从零构建一个与内部 ERP/CRM 深度集成、可长期迭代的定制化 AI 应用。应优先推荐哪款产品？
A. WorkBuddy（办公助理）
B. CodeBuddy（编程助手）
C. ADP（智能体开发平台）
D. Miora（创意工作室）
答案：C

示例 2（TROUBLESHOOTING 单选）
客户现场的 MCP Server 一直连不上（客户端显示红色状态）。按正确的排查思路，应该怎么查？
A. 按从外到内排查：先查网络出口、再查配置层级、最后查凭据与权限
B. 第一步就重写整个 MCP 配置文件，反复换地址直到连上
C. 红色状态大多是第三方服务不稳定，优先换一个同类 MCP Server
D. 红色状态基本都是凭据失效，直接重新生成 Token 即可
答案：A

示例 3（COMPARISON 多选）
一个能交付的 Harness 需要补齐「五件套」。下列属于五件套的有？
A. 工具接入——让模型能调用外部 API/数据库/搜索
B. 输入输出契约——定义输入 Schema 和输出 Schema 的校验
C. 模型微调——用客户数据持续训练专属模型
D. 护栏门禁——输入侧过滤敏感请求，输出侧检查合规性
答案：A、B、D
"""


class LLMError(RuntimeError):
    pass


def _strip_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        headers = {"User-Agent": settings.llm_user_agent}
        if "opencode.ai" in settings.llm_base_url:
            # OpenCode Go requires a stable session header for routing/caching.
            headers["x-opencode-session"] = settings.llm_session
        self.client = (
            OpenAI(
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                timeout=settings.llm_timeout,
                max_retries=settings.llm_max_retries,
                default_headers=headers,
            )
            if settings.llm_api_key
            else None
        )

    @property
    def available(self) -> bool:
        return self.client is not None

    def _chat(self, system: str, user: str, temperature: float | None = None) -> str:
        if not self.client:
            raise LLMError(
                "未配置 LLM Key。请在 generator/.env 配置 LLM_API_KEY 或 OPENAI_API_KEY。"
            )
        last_error: Exception | None = None
        for attempt in range(self.settings.llm_max_retries):
            try:
                response = self.client.chat.completions.create(
                    model=self.settings.llm_model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    temperature=(
                        self.settings.llm_temperature
                        if temperature is None
                        else temperature
                    ),
                    response_format={"type": "json_object"},
                )
                return response.choices[0].message.content or "{}"
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(min(8, 1.5 * (attempt + 1)))
        raise LLMError(f"LLM 调用失败：{last_error}") from last_error

    def generate_questions(
        self,
        *,
        chapter_title: str,
        section_title: str,
        chunk_content: str,
        source_page: int,
        existing_claims: list[str],
        n_single: int,
        n_multiple: int,
        difficulty: str = "MEDIUM",
        single_style: str = "SCENARIO",
        multiple_style: str = "COMPARISON",
    ) -> GeneratedQuestionBatch:
        claims = "\n".join(f"- {claim}" for claim in existing_claims[-20:]) or "（无）"
        user = f"""【章节】{chapter_title}
【小节】{section_title}
【难度】{difficulty}
【本次任务】生成 {n_single} 道单选题、{n_multiple} 道多选题。
【目标风格】
- 单选题：{single_style} —— {STYLE_GUIDE.get(single_style, "")}
- 多选题：{multiple_style} —— {STYLE_GUIDE.get(multiple_style, "")}

【课程原文】（片段前标注 PDF 页码）
[第 {source_page} 页]
{chunk_content}

【该知识点已考过的事实（禁止重复）】
{claims}

{FEW_SHOT_EXAMPLES}

只输出如下 JSON 结构：
{{
  "questions": [
    {{
      "type": "SINGLE",
      "style": "{single_style}",
      "stem": "题干（必须是场景/排查/对比/流程/口径/判断，不能是目录题）",
      "options": [
        {{"key": "A", "content": "选项A"}},
        {{"key": "B", "content": "选项B"}},
        {{"key": "C", "content": "选项C"}},
        {{"key": "D", "content": "选项D"}}
      ],
      "answer": ["B"],
      "explanation": "解析：说明为什么选 B，并指出其他选项错在哪里",
      "evidence_quote": "原文中的连续片段",
      "source_page": {source_page},
      "claim": "一句话概括本题考查的唯一规则/判断，不能是章节归属",
      "knowledge_point": "{section_title}",
      "difficulty": "{difficulty}"
    }},
    {{
      "type": "MULTIPLE",
      "style": "{multiple_style}",
      "stem": "题干（多选：下列说法正确的有/应包含哪些，必须有 2～3 个正确项）",
      "options": [
        {{"key": "A", "content": "选项A"}},
        {{"key": "B", "content": "选项B"}},
        {{"key": "C", "content": "选项C"}},
        {{"key": "D", "content": "选项D"}}
      ],
      "answer": ["A", "C"],
      "explanation": "解析：逐项说明正确项为什么对，至少两个错误项错在哪里",
      "evidence_quote": "原文中的连续片段",
      "source_page": {source_page},
      "claim": "一句话概括本题考查的唯一规则/判断，不能是章节归属",
      "knowledge_point": "{section_title}",
      "difficulty": "{difficulty}"
    }}
  ]
}}"""
        raw = self._chat(SYSTEM_PROMPT, user)
        return GeneratedQuestionBatch.model_validate_json(_strip_json(raw))

    def blind_solve(self, stem: str, options, is_multiple: bool) -> BlindResult:
        option_text = "\n".join(f"{o.key}. {o.content}" for o in options)
        user = f"""你是一名只掌握基础知识的考生。请只根据下面的题干和选项作答，不要猜测出题意图，不要使用外部知识。

【题干】
{stem}

【选项】
{option_text}

【要求】
- 单选题输出 1 个选项 key。
- 多选题输出 2～4 个选项 key。
- 如果不确定，给出最佳猜测，并标注 confidence（0～1）。
只输出 JSON：{{"answer": ["B"], "confidence": 0.8, "reason": "简要理由"}}"""
        raw = self._chat(
            "你是只根据题干和选项作答的考生。只输出 JSON。",
            user,
            temperature=0.1,
        )
        return BlindResult.model_validate_json(_strip_json(raw))

    def judge(
        self,
        *,
        evidence: str,
        stem: str,
        options,
        answer: list[str],
        explanation: str,
    ) -> JudgeResult:
        option_text = "\n".join(f"{o.key}. {o.content}" for o in options)
        user = f"""你是课程考试的审题专家。请根据原文证据，对题目进行 1～5 分评分。

【原文证据】
{evidence}

【题目】
{stem}
{option_text}
【标准答案】{", ".join(answer)}
【解析】{explanation}

评分维度：
1. grounded：事实是否完全由证据支持（5=完全支持，1=编造）
2. unambiguous：答案是否唯一且无歧义（5=非常明确，1=有争议）
3. clarity：题干是否清晰（5=非常清晰，1=难以理解）
4. distractor：干扰项是否合理（5=高质量，1=送分/荒谬）
5. difficulty_match：难度是否与标注一致（5=一致，1=严重不符）

只输出 JSON：
{{
  "grounded": 5,
  "unambiguous": 5,
  "clarity": 4,
  "distractor": 4,
  "difficulty_match": 4,
  "overall": 4.4,
  "verdict": "PASS",
  "issues": []
}}"""
        raw = self._chat(
            "你是严格的课程审题专家，只输出 JSON。",
            user,
            temperature=0.1,
        )
        return JudgeResult.model_validate_json(_strip_json(raw))

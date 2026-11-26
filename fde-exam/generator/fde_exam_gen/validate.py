from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from fde_exam_gen.models import GeneratedQuestion
from fde_exam_gen.normalize import normalize

BANNED_OPTION_PHRASES = [
    "以上都对",
    "以上都不对",
    "以上均是",
    "以上均不是",
    "以上都是",
    "以上都不是",
    "全部正确",
    "全部错误",
]

NAVIGATION_PATTERNS = [
    r"属于.{0,16}(章|小节|章节)",
    r"哪一项属于第\s*\d{1,3}\s*章",
    r"以下哪一项是第\s*\d{1,3}\s*章",
    r"以下哪些(小节|章节)",
    r"课程目录",
    r"位于第\s*\d{1,3}\s*章",
    r"章节归属",
    r"小节归属",
    r"第\s*\d{1,3}\s*章.{0,20}(包含|包括).{0,20}小节",
    r"以下哪一项.*(章|小节)的",
]

DEFINITION_PATTERNS = [
    r"^什么是",
    r"^什么叫",
    r"的定义是什么",
    r"是指什么",
    r"的含义是什么",
    r"^[^，。？]{0,20}是什么[？?]?$",
]

SCENARIO_MARKERS = [
    "某客户",
    "某团队",
    "某项目",
    "客户",
    "一线",
    "现场",
    "上线",
    "部署",
    "排查",
    "希望",
    "计划",
    "负责人",
    "业务方",
    "项目组",
    "团队",
]


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def reject(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def _option_map(question: GeneratedQuestion) -> dict[str, str]:
    return {option.key: option.content for option in question.options}


def _is_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def detect_style(stem: str) -> str:
    if re.search(
        r"连不上|报错|失败|异常|红色|排查|不生效|无法|故障|超时|拒绝|不见了|不触发",
        stem,
    ):
        return "TROUBLESHOOTING"
    if re.search(
        r"区别|对比|相比|更适合|优先推荐|选型|而不是|差异|哪个产品", stem
    ):
        return "COMPARISON"
    if re.search(r"顺序|步骤|阶段|先|再|最后|何时|什么时候|流程", stem):
        return "PROCESS"
    if re.search(r"积分|成本|耗时|多少|计算|口径|人月|费用", stem):
        return "CALCULATION"
    if any(marker in stem for marker in SCENARIO_MARKERS):
        return "SCENARIO"
    return "JUDGMENT"


def validate_question(
    question: GeneratedQuestion,
    *,
    chunk: dict | None,
    enforce_evidence: bool = True,
) -> ValidationResult:
    result = ValidationResult(ok=True)
    options = question.options
    keys = [option.key for option in options]
    option_map = _option_map(question)
    answers = sorted(set(question.answer))

    if question.type == "SINGLE":
        if len(options) != 4:
            result.reject("R01 单选题必须有 4 个选项")
        if len(answers) != 1:
            result.reject("R01 单选题必须有且仅有 1 个答案")
    else:
        if not (4 <= len(options) <= 6):
            result.reject("R02 多选题必须有 4～6 个选项")
        if not (2 <= len(answers) <= 4):
            result.reject("R02 多选题答案必须为 2～4 个")

    if len(keys) != len(set(keys)):
        result.reject("R03 选项 key 重复")
    if any(key not in option_map for key in answers):
        result.reject("R03 答案 key 不在选项中")
    if not answers:
        result.reject("R03 答案不能为空")

    normalized_options = [normalize(option.content) for option in options]
    if len(normalized_options) != len(set(normalized_options)):
        result.reject("R04 选项内容重复")

    for i, left in enumerate(normalized_options):
        for j, right in enumerate(normalized_options):
            if i == j or not left or not right:
                continue
            if left != right and left in right:
                result.reject("R05 选项存在包含关系")
                break

    for option in options:
        for phrase in BANNED_OPTION_PHRASES:
            if phrase in option.content:
                result.reject(f"R06 选项包含禁用表达：{phrase}")
        for phrase in BANNED_OPTION_PHRASES:
            if phrase in question.stem:
                result.reject(f"R06 题干包含禁用表达：{phrase}")

    normalized_stem = normalize(question.stem)
    for answer in answers:
        answer_text = normalize(option_map.get(answer, ""))
        if len(answer_text) >= 6 and answer_text in normalized_stem:
            result.reject("R07 题干包含答案原文")

    lengths = [len(option.content) for option in options]
    if min(lengths) > 0 and max(lengths) / min(lengths) > 2.5:
        result.warn("R08 选项长度差异较大")
    if sum(lengths) + len(question.stem) > 1200:
        result.reject("R09 题干与选项总长度超限")

    if not _is_chinese(question.stem):
        result.reject("R10 题干不是中文")
    if "\ufffd" in question.stem or "\ufffd" in question.explanation:
        result.reject("R10 文本包含乱码")

    if normalize(question.claim) == normalized_stem:
        result.reject("R12 claim 与题干相同")

    if re.search(r"(不是不|不能不|不会不|并非不|无不)", question.stem):
        result.warn("R14 题干可能包含双重否定")

    # R17: reject directory / chapter-section membership questions.
    if any(re.search(pattern, question.stem) for pattern in NAVIGATION_PATTERNS):
        result.reject("R17 禁止目录/章节归属类题目")
    section_style_options = sum(
        1
        for option in options
        if re.match(r"^\d{1,2}\.\d{1,2}\s+", option.content)
    )
    chapter_style_options = sum(
        1
        for option in options
        if re.match(r"^\d{1,2}\s+\S", option.content)
    )
    if section_style_options >= 2 or chapter_style_options >= 3:
        result.reject("R17 选项是章节/小节标题，属于目录题")

    # R18: reject bare definition questions without a scenario.
    stem_has_scenario = any(marker in question.stem for marker in SCENARIO_MARKERS)
    if any(re.search(pattern, question.stem) for pattern in DEFINITION_PATTERNS):
        if not stem_has_scenario:
            result.reject("R18 禁止无场景的纯定义题")

    # R19: keep style metadata accurate, but do not discard a good question
    # just because the model labelled its style incorrectly.
    detected_style = detect_style(question.stem)
    if detected_style != question.style:
        result.warn(
            f"R19 风格自动校正：{question.style} → {detected_style}"
        )
        question.style = detected_style  # type: ignore[assignment]

    # R20: multi-select must contain at least one wrong option.
    if question.type == "MULTIPLE" and len(answers) >= len(options):
        result.reject("R20 多选题必须至少有一个错误选项")

    if chunk is not None:
        if chunk.get("tableConfidence") == "LOW":
            result.reject("表格置信度低，不用于出题")
        page_start = chunk.get("pageStart")
        page_end = chunk.get("pageEnd") or page_start
        if page_start is not None and page_end is not None:
            if not (int(page_start) <= question.source_page <= int(page_end)):
                result.reject(
                    f"R15 source_page={question.source_page} 不在 chunk 页码范围 "
                    f"{page_start}～{page_end}"
                )
        if question.source_page <= 3:
            result.reject("R16 source_page 不能是封面/目录页")
        if enforce_evidence:
            content = str(chunk.get("content", ""))
            score = fuzz.partial_ratio(
                normalize(question.evidence_quote), normalize(content)
            )
            if score < 90:
                result.reject(f"R11 证据片段无法在原文块中匹配（{score:.0f}）")

    result.ok = len(result.errors) == 0
    return result

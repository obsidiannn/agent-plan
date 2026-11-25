from fde_exam_gen.models import GeneratedQuestion, OptionModel
from fde_exam_gen.validate import validate_question

CHUNK = {
    "content": "章节：01 概览与方法论\n小节：1.1 FDE 的本质定义\n\nFDE 是前置到客户一线、以工程手段直接交付解决方案的技术角色。",
    "pageStart": 4,
    "pageEnd": 5,
    "tableConfidence": None,
}


def question(**overrides):
    data = {
        "type": "SINGLE",
        "stem": "FDE 的核心工作方式是什么？",
        "options": [
            OptionModel(key="A", content="前置到客户一线交付解决方案"),
            OptionModel(key="B", content="只负责售前讲方案"),
            OptionModel(key="C", content="只负责写文档"),
            OptionModel(key="D", content="只负责项目管理"),
        ],
        "answer": ["A"],
        "explanation": "原文强调 FDE 要前置到客户一线，用工程手段交付。",
        "evidence_quote": "前置到客户一线、以工程手段直接交付解决方案",
        "source_page": 4,
        "claim": "FDE 前置到客户一线交付解决方案",
        "knowledge_point": "FDE 的本质定义",
        "difficulty": "EASY",
    }
    data.update(overrides)
    return GeneratedQuestion(**data)


def test_valid_question_passes():
    result = validate_question(question(), chunk=CHUNK)
    assert result.ok, result.errors


def test_single_choice_with_two_answers_rejected():
    result = validate_question(question(answer=["A", "B"]), chunk=CHUNK)
    assert not result.ok
    assert any("R01" in error for error in result.errors)


def test_banned_phrase_rejected():
    q = question()
    q.options[3].content = "以上都对"
    result = validate_question(q, chunk=CHUNK)
    assert not result.ok
    assert any("R06" in error for error in result.errors)


def test_source_page_out_of_chunk_range_rejected():
    result = validate_question(question(source_page=20), chunk=CHUNK)
    assert not result.ok
    assert any("R15" in error for error in result.errors)


def test_evidence_mismatch_rejected():
    result = validate_question(
        question(evidence_quote="这段证据在原文中完全不存在，只是编造的内容"),
        chunk=CHUNK,
    )
    assert not result.ok
    assert any("R11" in error for error in result.errors)

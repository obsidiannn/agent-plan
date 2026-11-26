from fde_exam_gen.models import GeneratedQuestion, OptionModel
from fde_exam_gen.normalize import content_hash, hamming, jaccard, normalize, simhash64


def make_question(stem: str, options: list[tuple[str, str]], answer: list[str]):
    return GeneratedQuestion(
        type="SINGLE",
        style="JUDGMENT",
        stem=stem,
        options=[OptionModel(key=key, content=content) for key, content in options],
        answer=answer,
        explanation="这是一段足够长的解析内容。",
        evidence_quote="这是一段足够长的原文证据片段。",
        source_page=5,
        claim="本题考查一个独立事实。",
        knowledge_point="测试",
        difficulty="EASY",
    )


def test_normalize_fullwidth_and_punctuation():
    assert normalize("  ＦＤＥ，考试！ ") == normalize("fde考试")


def test_content_hash_is_option_order_independent():
    left = make_question(
        "FDE 的核心角色是什么？",
        [("A", "Echo"), ("B", "Delta"), ("C", "其他"), ("D", "以上都不是")],
        ["A"],
    )
    right = make_question(
        "FDE 的核心角色是什么？",
        [("A", "Delta"), ("B", "其他"), ("C", "Echo"), ("D", "以上都不是")],
        ["C"],
    )
    assert content_hash(left) == content_hash(right)


def test_simhash_detects_rewrite():
    a = "FDE 的本质是什么？" + "这是一个关于前置部署工程师角色定义的说明" * 2
    b = "FDE 的本质指的是什么？" + "这是一个关于前置部署工程师角色定义的说明" * 2
    c = "请说明 Prompt 五要素分别是什么？" + "角色、指令、约束、示例和输出格式" * 2
    assert hamming(simhash64(a), simhash64(b)) <= 8
    assert hamming(simhash64(a), simhash64(c)) > 8


def test_jaccard_threshold():
    a = "客户落地四层门槛包括理解需求、翻译需求、零到一搭建和一到 N 调优"
    b = "客户落地四层门槛包括理解需求、翻译需求、零到一搭建和一到 N 调优"
    assert jaccard(a, b) == 1.0
    assert jaccard(a, "完全不同的另一段文本内容") < 0.2

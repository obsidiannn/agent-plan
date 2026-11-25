from __future__ import annotations

from collections import Counter

from fde_exam_gen.config import Settings
from fde_exam_gen.llm import LLMClient
from fde_exam_gen.models import GeneratedQuestion
from fde_exam_gen.normalize import normalize


def _same_answer(left: list[str], right: list[str]) -> bool:
    return sorted(set(left)) == sorted(set(right))


def blind_solve_consistency(
    client: LLMClient,
    settings: Settings,
    question: GeneratedQuestion,
) -> tuple[bool, dict]:
    samples = (
        settings.blind_samples_multiple if question.type == "MULTIPLE" else 1
    )
    answers: list[tuple[str, ...]] = []
    details = []
    for _ in range(max(1, samples)):
        result = client.blind_solve(
            question.stem,
            question.options,
            question.type == "MULTIPLE",
        )
        key = tuple(sorted(set(result.answer)))
        answers.append(key)
        details.append(
            {"answer": list(key), "confidence": result.confidence, "reason": result.reason}
        )
    if not answers:
        return False, {"samples": details}
    counter = Counter(answers)
    majority, count = counter.most_common(1)[0]
    consistent = count >= max(1, (len(answers) // 2) + 1)
    matches_key = _same_answer(list(majority), question.answer)
    return consistent and matches_key, {
        "samples": details,
        "majority": list(majority),
        "consistent": consistent,
        "matches_key": matches_key,
    }


def judge_quality(
    client: LLMClient,
    settings: Settings,
    question: GeneratedQuestion,
) -> tuple[bool, dict, float]:
    result = client.judge(
        evidence=question.evidence_quote,
        stem=question.stem,
        options=question.options,
        answer=question.answer,
        explanation=question.explanation,
    )
    weighted = (
        result.grounded * 0.30
        + result.unambiguous * 0.25
        + result.clarity * 0.20
        + result.distractor * 0.15
        + result.difficulty_match * 0.10
    )
    passed = (
        result.verdict == "PASS"
        and weighted >= settings.quality_min_overall
        and result.grounded >= settings.quality_min_core
        and result.unambiguous >= settings.quality_min_core
    )
    return passed, result.model_dump(), round(weighted, 2)


def similar_claim(
    claim: str,
    existing_claims: list[str],
    similarity_threshold: float,
) -> str | None:
    from rapidfuzz import fuzz

    target = normalize(claim)
    for existing in existing_claims:
        if fuzz.ratio(target, normalize(existing)) / 100 >= similarity_threshold:
            return existing
    return None

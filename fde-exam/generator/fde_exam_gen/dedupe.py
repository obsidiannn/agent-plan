from __future__ import annotations

from fde_exam_gen.config import Settings
from fde_exam_gen.models import GeneratedQuestion
from fde_exam_gen.normalize import claim_hash, content_hash, simhash64, simhash_hex
from fde_exam_gen.repository import Repository


def question_fingerprints(question: GeneratedQuestion, chapter_key: str) -> dict:
    option_text = "".join(sorted(option.content for option in question.options))
    sim = simhash64(question.stem + option_text)
    return {
        "content_hash": content_hash(question),
        "claim_hash": claim_hash(question, chapter_key),
        "simhash_int": sim,
        "simhash_hex": f"{sim:016x}",
    }


def check_duplicate(
    repo: Repository,
    settings: Settings,
    index: dict,
    question: GeneratedQuestion,
    chapter_key: str,
) -> tuple[str | None, dict]:
    fp = question_fingerprints(question, chapter_key)
    duplicate = repo.find_duplicate(
        index=index,
        content_hash=fp["content_hash"],
        claim_hash=fp["claim_hash"],
        simhash_value=fp["simhash_int"],
        hamming_threshold=settings.hamming_threshold,
    )
    return duplicate, fp


def add_to_index(index: dict, fp: dict) -> None:
    index["content_hashes"].add(fp["content_hash"])
    index["claim_hashes"].add(fp["claim_hash"])
    index["simhashes"].append(fp["simhash_int"])


def prepare_index(repo: Repository) -> dict:
    return repo.dedupe_index()


def scan_duplicates(repo: Repository, threshold: int) -> list[tuple]:
    return repo.list_duplicate_pairs(threshold)

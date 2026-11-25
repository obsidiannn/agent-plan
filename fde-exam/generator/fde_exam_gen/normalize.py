from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from fde_exam_gen.models import GeneratedQuestion


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE)
    return text


def content_hash(question: GeneratedQuestion) -> str:
    option_contents = sorted(normalize(o.content) for o in question.options)
    correct = sorted(
        normalize(o.content)
        for o in question.options
        if o.key in question.answer
    )
    payload = json.dumps(
        {
            "type": question.type,
            "stem": normalize(question.stem),
            "options": option_contents,
            "answers": correct,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def claim_hash(question: GeneratedQuestion, chapter_key: str) -> str:
    payload = f"{chapter_key}|{normalize(question.claim)}"
    return hashlib.sha256(payload.encode()).hexdigest()


def shingles(text: str, n: int = 3) -> set[str]:
    text = normalize(text)
    if len(text) <= n:
        return {text} if text else set()
    return {text[i : i + n] for i in range(len(text) - n + 1)}


def simhash64(text: str) -> int:
    vector = [0] * 64
    tokens = shingles(text)
    if not tokens:
        return 0
    for token in tokens:
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for i in range(64):
            vector[i] += 1 if (value >> i) & 1 else -1
    result = 0
    for i in range(64):
        if vector[i] > 0:
            result |= 1 << i
    return result


def simhash_hex(text: str) -> str:
    return f"{simhash64(text):016x}"


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def jaccard(a: str, b: str) -> float:
    sa, sb = shingles(a), shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)

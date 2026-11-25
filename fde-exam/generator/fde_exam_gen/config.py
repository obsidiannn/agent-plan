from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    if p.is_absolute():
        return p
    return (BASE_DIR / p).resolve()


@dataclass(frozen=True)
class Settings:
    db_path: Path
    source_pdf: Path
    source_out_dir: Path
    parser_version: str
    expected_pages: int
    expected_chapters: int
    ignore_pages: tuple[int, ...]

    llm_base_url: str
    llm_api_key: str
    llm_model: str
    llm_temperature: float
    llm_timeout: float
    llm_max_retries: int
    llm_session: str
    llm_user_agent: str

    hamming_threshold: int
    jaccard_threshold: float
    claim_similarity: float

    quality_min_overall: float
    quality_min_core: float
    blind_samples_multiple: int
    target_candidates: int


def load_settings() -> Settings:
    def env(name: str, default: str) -> str:
        return os.getenv(name, default)

    ignore = env("PDF_IGNORE_PAGES", "1-3")
    ignore_pages: set[int] = set()
    for part in ignore.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            ignore_pages.update(range(int(a), int(b) + 1))
        else:
            ignore_pages.add(int(part))

    # Prefer the OPENAI_* aliases when an OpenAI-compatible key is provided
    # (OpenCode Go uses OPENAI_BASE_URL / OPENAI_API_KEY). Otherwise use LLM_*.
    openai_key = env("OPENAI_API_KEY", "")
    llm_key = env("LLM_API_KEY", "")
    if openai_key:
        api_key = openai_key
        base_url = (
            env("OPENAI_BASE_URL", "")
            or env("LLM_BASE_URL", "")
            or "https://api.deepseek.com/v1"
        )
        model = env("OPENAI_MODEL", "") or env("LLM_MODEL", "")
    else:
        api_key = llm_key
        base_url = (
            env("LLM_BASE_URL", "")
            or env("OPENAI_BASE_URL", "")
            or "https://api.deepseek.com/v1"
        )
        model = env("LLM_MODEL", "") or env("OPENAI_MODEL", "")

    default_model = (
        "deepseek-v4.1-flash" if "opencode.ai" in base_url else "deepseek-chat"
    )
    if "opencode.ai" in base_url and model in {"", "deepseek-chat"}:
        model = default_model
    model = model or default_model
    # OpenCode Go asks clients to send a stable session id for routing/caching.
    session = (
        env("LLM_SESSION_ID", "")
        or env("OPENCODE_SESSION", "")
        or f"fde-exam-{uuid.uuid4().hex[:16]}"
    )

    return Settings(
        db_path=_resolve(env("DB_PATH", "../web/prisma/dev.db")),
        source_pdf=_resolve(env("SOURCE_PDF", "../doc/fde.pdf")),
        source_out_dir=_resolve(env("SOURCE_OUT_DIR", "../data/source")),
        parser_version=env("PDF_PARSER_VERSION", "pymupdf-1"),
        expected_pages=int(env("PDF_EXPECTED_PAGES", "151")),
        expected_chapters=int(env("PDF_EXPECTED_CHAPTERS", "12")),
        ignore_pages=tuple(sorted(ignore_pages)),
        llm_base_url=base_url,
        llm_api_key=api_key,
        llm_model=model,
        llm_temperature=float(env("LLM_TEMPERATURE", "0.4")),
        llm_timeout=float(env("LLM_TIMEOUT_SECONDS", "120")),
        llm_max_retries=int(env("LLM_MAX_RETRIES", "3")),
        llm_session=session,
        llm_user_agent=env("LLM_USER_AGENT", "fde-exam-generator/0.1"),
        hamming_threshold=int(env("DEDUP_HAMMING_THRESHOLD", "4")),
        jaccard_threshold=float(env("DEDUP_JACCARD_THRESHOLD", "0.85")),
        claim_similarity=float(env("DEDUP_CLAIM_SIMILARITY", "0.95")),
        quality_min_overall=float(env("QUALITY_MIN_OVERALL", "4.0")),
        quality_min_core=float(env("QUALITY_MIN_CORE", "4")),
        blind_samples_multiple=int(env("BLIND_SOLVE_SAMPLES_MULTIPLE", "3")),
        target_candidates=int(env("TARGET_CANDIDATES", "150")),
    )

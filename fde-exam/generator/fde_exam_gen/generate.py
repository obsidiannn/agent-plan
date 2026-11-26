from __future__ import annotations

import sqlite3

from fde_exam_gen.blueprint import build_units
from fde_exam_gen.config import Settings
from fde_exam_gen.dedupe import add_to_index, check_duplicate, prepare_index
from fde_exam_gen.llm import LLMClient, LLMError
from fde_exam_gen.quality import blind_solve_consistency, judge_quality
from fde_exam_gen.repository import Repository
from fde_exam_gen.validate import validate_question


def run_generation(
    settings: Settings,
    *,
    target: int,
    seed: int | None,
    prompt_version: str,
    chapter_filter: str | None = None,
    auto_approve: bool = False,
    single_style: str | None = None,
    multiple_style: str | None = None,
) -> dict:
    repo = Repository(settings.db_path)
    client = LLMClient(settings)
    if not client.available:
        raise LLMError(
            "未配置 LLM Key，无法生成题目。请在 generator/.env 配置 LLM_API_KEY 或 OPENAI_API_KEY。"
        )

    chapters = repo.chapters_with_chunks()
    if chapter_filter:
        chapters = [
            chapter for chapter in chapters if chapter_filter in chapter["title"]
        ]
    if not chapters:
        raise RuntimeError("没有可用的章节/分块，请先执行 ingest 并导入数据库")

    units = build_units(
        chapters,
        target,
        single_style_override=single_style,
        multiple_style_override=multiple_style,
    )
    run_id = repo.start_run(
        source_hash=_source_hash(repo),
        model=settings.llm_model,
        prompt_version=prompt_version,
        seed=seed,
        target_count=target,
    )
    index = prepare_index(repo)
    generated = 0
    accepted = 0
    rejected = 0
    section_claims: dict[str, list[str]] = {}

    for unit in units:
        chunk = repo.chunk_by_id(unit["chunkId"])
        if not chunk:
            continue
        try:
            batch = client.generate_questions(
                chapter_title=unit["chapterTitle"],
                section_title=unit["sectionTitle"],
                chunk_content=unit["chunkContent"],
                source_page=int(unit.get("pageStart") or 4),
                existing_claims=section_claims.get(unit["sectionTitle"], [])
                + repo.claims_for_chapter(unit["chapterId"]),
                n_single=unit["nSingle"],
                n_multiple=unit["nMultiple"],
                single_style=unit.get("singleStyle", "SCENARIO"),
                multiple_style=unit.get("multipleStyle", "COMPARISON"),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 生成失败：{unit['chapterTitle']} / {unit['section']}：{exc}")
            continue

        for question in batch.questions:
            generated += 1
            chapter_key = unit["chapterId"]
            duplicate, fp = check_duplicate(
                repo, settings, index, question, chapter_key
            )
            validation = validate_question(question, chunk=chunk)
            if duplicate:
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status=duplicate,
                    reason=f"去重命中：{duplicate}",
                )
                continue
            if not validation.ok:
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="RULE_REJECTED",
                    reason="；".join(validation.errors),
                )
                continue

            try:
                blind_ok, blind_detail = blind_solve_consistency(
                    client, settings, question
                )
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="QUALITY_REJECTED",
                    reason=f"盲测调用失败：{exc}",
                )
                continue
            if not blind_ok:
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="QUALITY_REJECTED",
                    reason="盲测作答与标准答案不一致",
                )
                continue

            try:
                judge_ok, judge_detail, quality_score = judge_quality(
                    client, settings, question
                )
            except Exception as exc:  # noqa: BLE001
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="QUALITY_REJECTED",
                    reason=f"质量评审调用失败：{exc}",
                )
                continue
            if not judge_ok:
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="QUALITY_REJECTED",
                    reason="LLM 质量评审未通过",
                )
                continue

            status = "APPROVED" if auto_approve else "PENDING_REVIEW"
            try:
                repo.insert_question_with_candidate(
                    question=question,
                    run_id=run_id,
                    chapter_id=unit["chapterId"],
                    source_chunk_id=unit["chunkId"],
                    source_ref=unit["sectionRef"],
                    source_page=question.source_page,
                    source_page_end=question.source_page,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status=status,
                    prompt_version=prompt_version,
                    quality_score=quality_score,
                    quality_detail={
                        "blind": blind_detail,
                        "judge": judge_detail,
                    },
                )
            except sqlite3.IntegrityError:
                rejected += 1
                repo.record_rejection(
                    run_id=run_id,
                    question=question,
                    content_hash=fp["content_hash"],
                    claim_hash=fp["claim_hash"],
                    simhash_hex=fp["simhash_hex"],
                    status="DUP_EXACT",
                    reason="并发写入时唯一约束拦截",
                )
                continue
            add_to_index(index, fp)
            section_claims.setdefault(unit["sectionTitle"], []).append(question.claim)
            accepted += 1

        if generated % 10 == 0:
            repo.update_run(
                run_id,
                generated=generated,
                accepted=accepted,
                rejected=rejected,
                status="RUNNING",
            )

    repo.update_run(
        run_id,
        generated=generated,
        accepted=accepted,
        rejected=rejected,
        status="SUCCESS",
    )
    result = {
        "runId": run_id,
        "generated": generated,
        "accepted": accepted,
        "rejected": rejected,
        "status": "SUCCESS",
    }
    repo.close()
    return result


def _source_hash(repo: Repository) -> str:
    row = repo.conn.execute(
        "SELECT contentHash FROM source_docs ORDER BY createdAt DESC LIMIT 1"
    ).fetchone()
    return row["contentHash"] if row else "unknown"

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from fde_exam_gen.models import GeneratedQuestion


def new_id(prefix: str = "c") -> str:
    return prefix + uuid.uuid4().hex


def now_sql() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


class Repository:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        if not db_path.exists():
            raise FileNotFoundError(
                f"数据库不存在：{db_path}\n请先在 web 目录执行 prisma migrate dev"
            )
        self.conn = sqlite3.connect(str(db_path), timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=5000")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._check_schema()

    def close(self) -> None:
        self.conn.close()

    def _check_schema(self) -> None:
        required = {
            "source_docs",
            "chapters",
            "source_chunks",
            "questions",
            "question_candidates",
            "generation_runs",
        }
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        existing = {row["name"] for row in rows}
        missing = required - existing
        if missing:
            raise RuntimeError(f"数据库缺少表：{', '.join(sorted(missing))}")

    @contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- source / chapters / chunks ----------
    def source_exists(self, content_hash: str) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM source_docs WHERE contentHash = ?", (content_hash,)
        ).fetchone()

    def insert_source(
        self,
        *,
        title: str,
        url: str | None,
        file_path: str,
        file_hash: str,
        page_count: int,
        content_hash: str,
        word_count: int,
    ) -> str:
        source_id = new_id("sd")
        self.conn.execute(
            """
            INSERT INTO source_docs
              (id, title, url, format, filePath, fileHash, pageCount, contentHash, wordCount, createdAt)
            VALUES (?, ?, ?, 'PDF', ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                title,
                url,
                file_path,
                file_hash,
                page_count,
                content_hash,
                word_count,
                now_sql(),
            ),
        )
        self.conn.commit()
        return source_id

    def insert_chapter(
        self,
        *,
        source_id: str,
        order_no: int,
        title: str,
        weight: float,
        page_start: int,
        page_end: int,
        anchor: str,
    ) -> str:
        chapter_id = new_id("ch")
        self.conn.execute(
            """
            INSERT INTO chapters
              (id, docId, title, orderNo, weight, pageStart, pageEnd, anchor)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chapter_id,
                source_id,
                title,
                order_no,
                weight,
                page_start,
                page_end,
                anchor,
            ),
        )
        return chapter_id

    def insert_chunk(
        self,
        *,
        chapter_id: str,
        order_no: int,
        content: str,
        content_hash: str,
        token_count: int,
        page_start: int,
        page_end: int,
        section_ref: str | None,
        table_confidence: str | None,
    ) -> str:
        chunk_id = new_id("ck")
        self.conn.execute(
            """
            INSERT INTO source_chunks
              (id, chapterId, orderNo, content, contentHash, tokenCount, pageStart, pageEnd, sectionRef, tableConfidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk_id,
                chapter_id,
                order_no,
                content,
                content_hash,
                token_count,
                page_start,
                page_end,
                section_ref,
                table_confidence,
            ),
        )
        return chunk_id

    def commit(self) -> None:
        self.conn.commit()

    def chapters_with_chunks(self) -> list[dict]:
        chapters = self.conn.execute(
            "SELECT * FROM chapters ORDER BY orderNo"
        ).fetchall()
        result: list[dict] = []
        for chapter in chapters:
            chunks = self.conn.execute(
                "SELECT * FROM source_chunks WHERE chapterId = ? ORDER BY orderNo",
                (chapter["id"],),
            ).fetchall()
            result.append(
                {
                    "id": chapter["id"],
                    "orderNo": chapter["orderNo"],
                    "title": chapter["title"],
                    "weight": chapter["weight"],
                    "pageStart": chapter["pageStart"],
                    "pageEnd": chapter["pageEnd"],
                    "chunks": [dict(chunk) for chunk in chunks],
                }
            )
        return result

    def claims_for_chapter(self, chapter_id: str, limit: int = 40) -> list[str]:
        rows = self.conn.execute(
            """
            SELECT q.claim FROM questions q
            WHERE q.chapterId = ?
            ORDER BY q.createdAt DESC
            LIMIT ?
            """,
            (chapter_id, limit),
        ).fetchall()
        return [row["claim"] for row in rows if row["claim"]]

    def chunk_by_id(self, chunk_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM source_chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        return dict(row) if row else None

    # ---------- generation runs ----------
    def start_run(
        self,
        *,
        source_hash: str,
        model: str,
        prompt_version: str,
        seed: int | None,
        target_count: int,
    ) -> str:
        run_id = new_id("run")
        self.conn.execute(
            """
            INSERT INTO generation_runs
              (id, sourceHash, model, promptVersion, seed, targetCount, status, startedAt)
            VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?)
            """,
            (run_id, source_hash, model, prompt_version, seed, target_count, now_sql()),
        )
        self.conn.commit()
        return run_id

    def update_run(
        self,
        run_id: str,
        *,
        generated: int,
        accepted: int,
        rejected: int,
        status: str,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE generation_runs
            SET generatedCount = ?, acceptedCount = ?, rejectedCount = ?,
                status = ?, errorMessage = ?, finishedAt = ?
            WHERE id = ?
            """,
            (generated, accepted, rejected, status, error, now_sql(), run_id),
        )
        self.conn.commit()

    # ---------- dedupe ----------
    def dedupe_index(self) -> dict:
        content_hashes: set[str] = set()
        claim_hashes: set[str] = set()
        simhashes: list[int] = []
        for table in ("questions", "question_candidates"):
            rows = self.conn.execute(
                f"SELECT contentHash, claimHash, simhash FROM {table}"
            ).fetchall()
            for row in rows:
                if row["contentHash"]:
                    content_hashes.add(row["contentHash"])
                if row["claimHash"]:
                    claim_hashes.add(row["claimHash"])
                if row["simhash"]:
                    try:
                        simhashes.append(int(row["simhash"], 16))
                    except ValueError:
                        pass
        return {
            "content_hashes": content_hashes,
            "claim_hashes": claim_hashes,
            "simhashes": simhashes,
        }

    def find_duplicate(
        self,
        *,
        index: dict,
        content_hash: str,
        claim_hash: str,
        simhash_value: int,
        hamming_threshold: int,
    ) -> str | None:
        if content_hash in index["content_hashes"]:
            return "DUP_EXACT"
        for existing in index["simhashes"]:
            if (existing ^ simhash_value).bit_count() <= hamming_threshold:
                return "DUP_NEAR"
        if claim_hash in index["claim_hashes"]:
            return "DUP_CLAIM"
        return None

    def insert_candidate(
        self,
        *,
        run_id: str | None,
        question_type: str,
        content_hash: str,
        claim_hash: str | None,
        simhash_hex: str | None,
        status: str,
        reject_reason: str | None = None,
        question_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO question_candidates
              (id, runId, type, contentHash, claimHash, simhash, status, rejectReason, questionId, createdAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("qc"),
                run_id,
                question_type,
                content_hash,
                claim_hash,
                simhash_hex,
                status,
                reject_reason,
                question_id,
                now_sql(),
            ),
        )

    # ---------- questions ----------
    def insert_question(
        self,
        *,
        question: GeneratedQuestion,
        chapter_id: str | None,
        source_chunk_id: str | None,
        source_ref: str | None,
        source_page: int | None,
        source_page_end: int | None,
        content_hash: str,
        claim_hash: str,
        simhash_hex: str,
        status: str,
        generation_run_id: str | None,
        prompt_version: str | None,
        quality_score: float | None = None,
        quality_detail: dict | None = None,
        reject_reason: str | None = None,
    ) -> str:
        question_id = new_id("q")
        options_json = json.dumps(
            [{"key": option.key, "content": option.content} for option in question.options],
            ensure_ascii=False,
        )
        answer_json = json.dumps(question.answer, ensure_ascii=False)
        timestamp = now_sql()
        self.conn.execute(
            """
            INSERT INTO questions
              (id, type, style, stem, optionsJson, answerJson, explanation, difficulty,
               chapterId, knowledgePoint, sourceChunkId, evidenceQuote, sourceRef,
               sourcePage, sourcePageEnd, contentHash, claim, claimHash, simhash,
               dedupeMetaJson, status, rejectReason, qualityScore, qualityDetailJson,
               generationRunId, promptVersion, version, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
            """,
            (
                question_id,
                question.type,
                question.style,
                question.stem,
                options_json,
                answer_json,
                question.explanation,
                question.difficulty,
                chapter_id,
                question.knowledge_point,
                source_chunk_id,
                question.evidence_quote,
                source_ref,
                source_page,
                source_page_end,
                content_hash,
                question.claim,
                claim_hash,
                simhash_hex,
                None,
                status,
                reject_reason,
                quality_score,
                json.dumps(quality_detail, ensure_ascii=False) if quality_detail else None,
                generation_run_id,
                prompt_version,
                timestamp,
                timestamp,
            ),
        )
        return question_id

    def insert_question_with_candidate(
        self,
        *,
        question: GeneratedQuestion,
        run_id: str | None,
        chapter_id: str | None,
        source_chunk_id: str | None,
        source_ref: str | None,
        source_page: int | None,
        source_page_end: int | None,
        content_hash: str,
        claim_hash: str,
        simhash_hex: str,
        status: str,
        prompt_version: str | None,
        quality_score: float | None = None,
        quality_detail: dict | None = None,
    ) -> str:
        with self.transaction() as conn:
            question_id = self.insert_question(
                question=question,
                chapter_id=chapter_id,
                source_chunk_id=source_chunk_id,
                source_ref=source_ref,
                source_page=source_page,
                source_page_end=source_page_end,
                content_hash=content_hash,
                claim_hash=claim_hash,
                simhash_hex=simhash_hex,
                status=status,
                generation_run_id=run_id,
                prompt_version=prompt_version,
                quality_score=quality_score,
                quality_detail=quality_detail,
            )
            self.insert_candidate(
                run_id=run_id,
                question_type=question.type,
                content_hash=content_hash,
                claim_hash=claim_hash,
                simhash_hex=simhash_hex,
                status="ACCEPTED" if status != "REJECTED" else "REVIEW_REJECTED",
                question_id=question_id,
            )
            return question_id

    def record_rejection(
        self,
        *,
        run_id: str | None,
        question: GeneratedQuestion,
        content_hash: str,
        claim_hash: str,
        simhash_hex: str,
        status: str,
        reason: str,
    ) -> None:
        self.insert_candidate(
            run_id=run_id,
            question_type=question.type,
            content_hash=content_hash,
            claim_hash=claim_hash,
            simhash_hex=simhash_hex,
            status=status,
            reject_reason=reason,
        )
        self.conn.commit()

    # ---------- reporting / admin ----------
    def stats(self) -> dict:
        counts = {}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM questions GROUP BY status"
        ).fetchall():
            counts[row["status"]] = row["n"]
        by_type = {}
        for row in self.conn.execute(
            "SELECT type, COUNT(*) AS n FROM questions WHERE status='APPROVED' GROUP BY type"
        ).fetchall():
            by_type[row["type"]] = row["n"]
        candidates = {}
        for row in self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM question_candidates GROUP BY status"
        ).fetchall():
            candidates[row["status"]] = row["n"]
        chapters = self.conn.execute("SELECT COUNT(*) AS n FROM chapters").fetchone()["n"]
        chunks = self.conn.execute("SELECT COUNT(*) AS n FROM source_chunks").fetchone()["n"]
        styles = {}
        for row in self.conn.execute(
            "SELECT COALESCE(style, 'UNKNOWN') AS style, COUNT(*) AS n "
            "FROM questions WHERE status='APPROVED' GROUP BY style"
        ).fetchall():
            styles[row["style"]] = row["n"]
        return {
            "questions": counts,
            "approvedByType": by_type,
            "approvedByStyle": styles,
            "candidates": candidates,
            "chapters": chapters,
            "chunks": chunks,
        }

    def list_duplicate_pairs(self, threshold: int = 4) -> list[tuple]:
        rows = self.conn.execute(
            "SELECT id, stem, simhash, status FROM questions WHERE simhash IS NOT NULL"
        ).fetchall()
        pairs = []
        for i, left in enumerate(rows):
            lh = int(left["simhash"], 16)
            for right in rows[i + 1 :]:
                rh = int(right["simhash"], 16)
                distance = (lh ^ rh).bit_count()
                if distance <= threshold:
                    pairs.append(
                        (
                            distance,
                            left["id"],
                            left["status"],
                            left["stem"],
                            right["id"],
                            right["status"],
                            right["stem"],
                        )
                    )
        pairs.sort(key=lambda item: item[0])
        return pairs

    def export_review_csv(self, status: str = "PENDING_REVIEW") -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT q.id, q.type, q.stem, q.optionsJson, q.answerJson, q.explanation,
                   q.evidenceQuote, q.sourcePage, q.qualityScore, q.status,
                   c.title AS chapterTitle
            FROM questions q
            LEFT JOIN chapters c ON c.id = q.chapterId
            WHERE q.status = ?
            ORDER BY q.createdAt
            """,
            (status,),
        ).fetchall()
        return [dict(row) for row in rows]

    def set_question_status(
        self,
        question_id: str,
        status: str,
        reviewed_by: str,
        note: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE questions
            SET status = ?, reviewedBy = ?, reviewedAt = ?, reviewNote = ?,
                rejectReason = CASE WHEN ? = 'REJECTED' THEN ? ELSE NULL END,
                updatedAt = ?
            WHERE id = ?
            """,
            (
                status,
                reviewed_by,
                now_sql(),
                note,
                status,
                note or "批量退回",
                now_sql(),
                question_id,
            ),
        )

    def commit_changes(self) -> None:
        self.conn.commit()

    def purge_prompt_versions(self, versions: Iterable[str]) -> dict:
        versions = list(versions)
        if not versions:
            return {"questions": 0, "candidates": 0, "runs": 0}
        placeholders = ",".join("?" for _ in versions)
        with self.transaction():
            question_rows = self.conn.execute(
                f"SELECT id FROM questions WHERE promptVersion IN ({placeholders})",
                versions,
            ).fetchall()
            question_ids = [row["id"] for row in question_rows]
            candidate_count = self.conn.execute(
                f"SELECT COUNT(*) AS n FROM question_candidates WHERE questionId IN "
                f"(SELECT id FROM questions WHERE promptVersion IN ({placeholders}))",
                versions,
            ).fetchone()["n"]
            run_rows = self.conn.execute(
                f"SELECT id FROM generation_runs WHERE promptVersion IN ({placeholders})",
                versions,
            ).fetchall()
            run_ids = [row["id"] for row in run_rows]
            self.conn.execute(
                f"DELETE FROM question_candidates WHERE questionId IN "
                f"(SELECT id FROM questions WHERE promptVersion IN ({placeholders}))",
                versions,
            )
            self.conn.execute(
                f"DELETE FROM question_candidates WHERE runId IN "
                f"(SELECT id FROM generation_runs WHERE promptVersion IN ({placeholders}))",
                versions,
            )
            if question_ids:
                q_placeholders = ",".join("?" for _ in question_ids)
                self.conn.execute(
                    f"UPDATE attempt_questions SET questionId = NULL "
                    f"WHERE questionId IN ({q_placeholders})",
                    question_ids,
                )
                self.conn.execute(
                    f"DELETE FROM questions WHERE id IN ({q_placeholders})",
                    question_ids,
                )
            self.conn.execute(
                f"DELETE FROM generation_runs WHERE promptVersion IN ({placeholders})",
                versions,
            )
        return {
            "questions": len(question_ids),
            "candidates": candidate_count,
            "runs": len(run_ids),
        }

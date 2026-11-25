from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from fde_exam_gen.config import Settings
from fde_exam_gen.models import Chunk
from fde_exam_gen.pdf_parser import build_chunks, chapter_weight, parse_pdf
from fde_exam_gen.repository import Repository


def _structure_payload(pdf_path: Path, parsed, chunks: list[Chunk]) -> dict:
    total_sections = sum(len(chapter.sections) for chapter in parsed.chapters)
    chapters = []
    for chapter in parsed.chapters:
        chapters.append(
            {
                "orderNo": chapter.order_no,
                "title": chapter.title,
                "anchor": chapter.anchor,
                "pageStart": chapter.page_start,
                "pageEnd": chapter.page_end,
                "weight": chapter_weight(chapter, total_sections),
                "sections": [
                    {
                        "ref": section.ref,
                        "title": section.title,
                        "pageStart": section.page_start,
                        "pageEnd": section.page_end,
                        "anchor": f"sec-{chapter.order_no}-{section.ref.split('.')[-1]}"
                        if section.ref
                        else None,
                    }
                    for section in chapter.sections
                ],
            }
        )
    return {
        "source": {
            "file": str(pdf_path),
            "title": parsed.title,
            "pages": parsed.page_count,
            "sha256": parsed.file_hash,
            "parsedAt": datetime.now(timezone.utc).isoformat(),
            "parserVersion": "pymupdf-1",
        },
        "chapters": chapters,
        "chunkCount": len(chunks),
    }


def _markdown(parsed, chunks: list[Chunk]) -> str:
    lines = [
        f"# {parsed.title}",
        "",
        f"> 来源：{parsed.page_count} 页 PDF，共 {len(parsed.chapters)} 章。",
        "",
    ]
    for chapter in parsed.chapters:
        lines.append(f"## {chapter.title}")
        lines.append("")
        for block in chapter.blocks:
            lines.append(block.text)
            lines.append("")
        for section in chapter.sections:
            lines.append(f"### {section.title}")
            lines.append("")
            for block in section.blocks:
                if block.kind == "subhead":
                    lines.append(f"#### {block.text}")
                else:
                    lines.append(block.text)
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def run_ingest(settings: Settings) -> dict:
    settings.source_out_dir.mkdir(parents=True, exist_ok=True)
    image_dir = settings.source_out_dir / "images"
    parsed = parse_pdf(
        settings.source_pdf,
        image_dir=image_dir,
        ignore_pages=settings.ignore_pages,
    )
    if parsed.page_count != settings.expected_pages:
        raise ValueError(
            f"PDF 页数不符：期望 {settings.expected_pages}，实际 {parsed.page_count}"
        )
    if len(parsed.chapters) != settings.expected_chapters:
        raise ValueError(
            f"章节数不符：期望 {settings.expected_chapters}，实际 {len(parsed.chapters)}"
        )

    chunks = build_chunks(parsed.chapters)
    structure = _structure_payload(settings.source_pdf, parsed, chunks)
    markdown = _markdown(parsed, chunks)

    (settings.source_out_dir / "fde.md").write_text(markdown, encoding="utf-8")
    (settings.source_out_dir / "fde.structure.json").write_text(
        json.dumps(structure, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (settings.source_out_dir / "fde.meta.json").write_text(
        json.dumps(
            {
                "source": structure["source"],
                "pages": parsed.page_count,
                "chapters": len(parsed.chapters),
                "sections": sum(len(chapter.sections) for chapter in parsed.chapters),
                "chunks": len(chunks),
                "tables": parsed.table_count,
                "lowConfidenceTables": parsed.low_confidence_tables,
                "images": len(parsed.images),
                "imageFiles": parsed.images,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "title": parsed.title,
        "fileHash": parsed.file_hash,
        "pages": parsed.page_count,
        "wordCount": len(markdown),
        "chapters": len(parsed.chapters),
        "sections": structure["chapters"],
        "chunks": [
            {
                "chapterOrder": chunk.chapter_order,
                "chapterTitle": chunk.chapter_title,
                "sectionRef": chunk.section_ref,
                "sectionTitle": chunk.section_title,
                "orderNo": chunk.order_no,
                "content": chunk.content,
                "pageStart": chunk.page_start,
                "pageEnd": chunk.page_end,
                "tableConfidence": chunk.table_confidence,
                "contentHash": __import__("hashlib").sha256(
                    chunk.content.encode()
                ).hexdigest(),
            }
            for chunk in chunks
        ],
        "tables": parsed.table_count,
        "lowConfidenceTables": parsed.low_confidence_tables,
        "images": len(parsed.images),
        "markdownPath": str(settings.source_out_dir / "fde.md"),
        "structurePath": str(settings.source_out_dir / "fde.structure.json"),
    }


def import_ingest(settings: Settings, result: dict) -> dict:
    """Import the parsed structure and chunks into the Prisma-managed SQLite DB."""
    markdown_path = Path(result["markdownPath"])
    markdown = markdown_path.read_text(encoding="utf-8")
    content_hash = hashlib.sha256(markdown.encode()).hexdigest()

    repo = Repository(settings.db_path)
    existing = repo.source_exists(content_hash)
    if existing:
        chapter_rows = repo.conn.execute(
            "SELECT id, orderNo, title FROM chapters WHERE docId = ? ORDER BY orderNo",
            (existing["id"],),
        ).fetchall()
        summary = {
            "sourceId": existing["id"],
            "chapters": len(chapter_rows),
            "chunks": repo.conn.execute(
                "SELECT COUNT(*) AS n FROM source_chunks sc "
                "JOIN chapters c ON c.id = sc.chapterId WHERE c.docId = ?",
                (existing["id"],),
            ).fetchone()["n"],
            "imported": False,
        }
        repo.close()
        return summary

    source_id = repo.insert_source(
        title=result["title"],
        url="https://cloud.tencent.com/edu/learning/course-4767-84816-84841",
        file_path=str(settings.source_pdf),
        file_hash=result["fileHash"],
        page_count=result["pages"],
        content_hash=content_hash,
        word_count=result.get("wordCount", 0),
    )

    chapter_ids: dict[int, str] = {}
    for chapter in result["sections"]:
        chapter_id = repo.insert_chapter(
            source_id=source_id,
            order_no=chapter["orderNo"],
            title=chapter["title"],
            weight=float(chapter.get("weight", 1)),
            page_start=int(chapter["pageStart"]),
            page_end=int(chapter["pageEnd"]),
            anchor=chapter.get("anchor") or f"sec-{chapter['orderNo']}",
        )
        chapter_ids[chapter["orderNo"]] = chapter_id

    for chunk in result["chunks"]:
        chapter_id = chapter_ids.get(chunk["chapterOrder"])
        if not chapter_id:
            continue
        repo.insert_chunk(
            chapter_id=chapter_id,
            order_no=chunk["orderNo"],
            content=chunk["content"],
            content_hash=chunk["contentHash"],
            token_count=max(1, len(chunk["content"]) // 2),
            page_start=int(chunk["pageStart"]),
            page_end=int(chunk["pageEnd"]),
            section_ref=chunk.get("sectionRef"),
            table_confidence=chunk.get("tableConfidence"),
        )
    repo.commit()
    repo.close()
    return {
        "sourceId": source_id,
        "chapters": len(chapter_ids),
        "chunks": len(result["chunks"]),
        "imported": True,
    }

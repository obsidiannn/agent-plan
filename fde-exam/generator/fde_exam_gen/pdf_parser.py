from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pymupdf as fitz

from fde_exam_gen.models import (
    Chapter,
    Chunk,
    ParsedDocument,
    Section,
    TextBlock,
)

FOOTER_RE = re.compile(r"^FDE Course Notes\s*\|\s*\d+\s*/\s*\d+$", re.I)
CHAPTER_RE = re.compile(r"^(\d{1,2})\s+(\S.*)$")
SECTION_RE = re.compile(r"^(\d{1,2}\.\d{1,2})\s+(\S.*)$")
BULLET_RE = re.compile(r"^(\d+[.、)]|[•·\-–—])\s*")

EXPECTED_CHAPTERS = [
    (1, "01 概览与方法论", 4),
    (2, "02 腾讯云AI重点产品介绍", 14),
    (3, "03 人工智能工程", 28),
    (4, "04 WorkBuddy 上手实操", 40),
    (5, "05 管理端：企业后台与 WMA 配置实战", 49),
    (6, "06 进场：挖真需求、破一线抵触", 66),
    (7, "07 交付：做成、且验得动", 82),
    (8, "08 沉淀：把经验变成组织资产", 97),
    (9, "09 综合实战：12 周 FDE 养成计划", 111),
    (10, "10 安全治理与护栏", 124),
    (11, "11 案例实战：企业 CFO 财务结算审核", 137),
    (12, "12 关键问题 FAQ", 144),
]


def _clean_line(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\x00", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _block_text(block: dict) -> tuple[str, float]:
    lines: list[str] = []
    max_size = 0.0
    for line in block.get("lines", []):
        pieces: list[str] = []
        for span in line.get("spans", []):
            max_size = max(max_size, float(span.get("size", 0)))
            pieces.append(str(span.get("text", "")))
        text = _clean_line("".join(pieces))
        if text:
            lines.append(text)
    if not lines:
        return "", max_size
    merged = ""
    for line in lines:
        if not merged:
            merged = line
            continue
        if BULLET_RE.match(line) or merged.endswith(("。", "！", "？", "；", "：", "”", "」")):
            merged += "\n" + line
        else:
            merged += line
    return merged.strip(), max_size


def _intersects_table(bbox: tuple[float, float, float, float], tables: list[tuple]) -> bool:
    x0, y0, x1, y1 = bbox
    center_x, center_y = (x0 + x1) / 2, (y0 + y1) / 2
    for tx0, ty0, tx1, ty1 in tables:
        if tx0 - 2 <= center_x <= tx1 + 2 and ty0 - 2 <= center_y <= ty1 + 2:
            return True
        ix0, iy0 = max(x0, tx0), max(y0, ty0)
        ix1, iy1 = min(x1, tx1), min(y1, ty1)
        if ix1 > ix0 and iy1 > iy0:
            inter = (ix1 - ix0) * (iy1 - iy0)
            area = max(1.0, (x1 - x0) * (y1 - y0))
            if inter / area > 0.5:
                return True
    return False


def _table_to_markdown(rows: list[list[object]]) -> tuple[str, str]:
    cleaned = [[_clean_cell(cell) for cell in row] for row in rows]
    cleaned = [row for row in cleaned if any(cell for cell in row)]
    if len(cleaned) < 2:
        return "", "LOW"
    width = max(len(row) for row in cleaned)
    confidence = "HIGH"
    if any(len(row) != width for row in cleaned):
        confidence = "LOW"
    normalized = [row + [""] * (width - len(row)) for row in cleaned]
    header = normalized[0]
    lines = [
        "| " + " | ".join(cell.replace("|", "\\|") for cell in header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    for row in normalized[1:]:
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in row) + " |")
    return "\n".join(lines), confidence


def _is_noise(text: str, size: float) -> bool:
    if FOOTER_RE.match(text):
        return True
    if size <= 9.2 and (
        text.startswith("第 ") and "章" in text
    ):
        return True
    if size <= 8.7 and text.lower().startswith("chapter "):
        return True
    if text in {"目录"}:
        return True
    return False


def parse_pdf(
    pdf_path: Path,
    image_dir: Path | None = None,
    ignore_pages: tuple[int, ...] = (1, 2, 3),
) -> ParsedDocument:
    doc = fitz.open(pdf_path)
    file_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    images: list[dict] = []
    table_count = 0
    low_confidence_tables = 0
    page_blocks: list[TextBlock] = []

    if image_dir is not None:
        image_dir.mkdir(parents=True, exist_ok=True)

    for page_index in range(doc.page_count):
        page_no = page_index + 1
        if page_no in ignore_pages:
            continue
        page = doc[page_index]

        table_bboxes: list[tuple] = []
        tables_on_page: list[TextBlock] = []
        try:
            finder = page.find_tables()
            for t_index, table in enumerate(finder.tables):
                table_bboxes.append(tuple(table.bbox))
                markdown, confidence = _table_to_markdown(table.extract())
                if not markdown:
                    continue
                table_count += 1
                if confidence == "LOW":
                    low_confidence_tables += 1
                tables_on_page.append(
                    TextBlock(
                        page=page_no,
                        text=markdown,
                        kind="table",
                        table_confidence=confidence,
                        y=float(table.bbox[1]),
                    )
                )
        except Exception:
            table_bboxes = []

        blocks: list[TextBlock] = []
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            bbox = tuple(block.get("bbox", (0, 0, 0, 0)))
            if _intersects_table(bbox, table_bboxes):
                continue
            text, size = _block_text(block)
            if not text or _is_noise(text, size):
                continue
            # A line-level footer can be mixed into a block; remove it.
            lines = [line for line in text.splitlines() if not FOOTER_RE.match(line.strip())]
            text = "\n".join(lines).strip()
            if not text:
                continue
            kind = "paragraph"
            if size >= 20 and CHAPTER_RE.match(text.splitlines()[0]):
                kind = "chapter"
            elif size >= 13.5 and SECTION_RE.match(text.splitlines()[0]):
                kind = "section"
            elif size >= 12.2 and len(text) <= 32 and "\n" not in text:
                kind = "subhead"
            blocks.append(
                TextBlock(
                    page=page_no,
                    text=text,
                    kind=kind,  # type: ignore[arg-type]
                    y=float(bbox[1]),
                )
            )

        page_blocks.extend(sorted(blocks + tables_on_page, key=lambda item: item.y))

        if image_dir is not None:
            for index, image in enumerate(page.get_images(full=True)):
                xref = image[0]
                try:
                    base = doc.extract_image(xref)
                except Exception:
                    continue
                if not base or not base.get("image"):
                    continue
                ext = base.get("ext", "png")
                filename = f"p{page_no:03d}-{index:02d}.{ext}"
                target = image_dir / filename
                if not target.exists():
                    target.write_bytes(base["image"])
                images.append(
                    {
                        "page": page_no,
                        "xref": xref,
                        "file": filename,
                        "width": base.get("width"),
                        "height": base.get("height"),
                    }
                )

    title = "腾讯云人工智能前沿部署工程师（FDE）"
    chapters = _build_structure(page_blocks, doc.page_count)

    return ParsedDocument(
        title=title,
        page_count=doc.page_count,
        file_hash=file_hash,
        chapters=chapters,
        images=images,
        table_count=table_count,
        low_confidence_tables=low_confidence_tables,
    )


def _build_structure(blocks: list[TextBlock], page_count: int) -> list[Chapter]:
    chapters: list[Chapter] = []
    current_chapter: Chapter | None = None
    current_section: Section | None = None

    for block in blocks:
        first_line = block.text.splitlines()[0] if block.text else ""
        if block.kind == "chapter":
            match = CHAPTER_RE.match(first_line)
            if not match:
                continue
            order_no = int(match.group(1))
            title = first_line.strip()
            current_chapter = Chapter(
                order_no=order_no,
                title=title,
                page_start=block.page,
                page_end=page_count,
                anchor=f"sec-{order_no}",
            )
            current_section = None
            chapters.append(current_chapter)
            continue

        if current_chapter is None:
            continue

        if block.kind == "section":
            match = SECTION_RE.match(first_line)
            if not match:
                continue
            current_section = Section(
                ref=match.group(1),
                title=first_line.strip(),
                page_start=block.page,
                page_end=page_count,
            )
            current_chapter.sections.append(current_section)
            continue

        if current_section is not None:
            current_section.blocks.append(block)
        else:
            current_chapter.blocks.append(block)

    if len(chapters) != len(EXPECTED_CHAPTERS):
        chapters = _fallback_structure(blocks, page_count)

    for index, chapter in enumerate(chapters):
        chapter.page_end = (
            chapters[index + 1].page_start - 1 if index + 1 < len(chapters) else page_count
        )
        for s_index, section in enumerate(chapter.sections):
            section.page_end = (
                chapter.sections[s_index + 1].page_start - 1
                if s_index + 1 < len(chapter.sections)
                else chapter.page_end
            )
            if section.page_end < section.page_start:
                section.page_end = section.page_start
    return chapters


def _fallback_structure(blocks: list[TextBlock], page_count: int) -> list[Chapter]:
    chapters: list[Chapter] = []
    for index, (order_no, title, start) in enumerate(EXPECTED_CHAPTERS):
        end = (
            EXPECTED_CHAPTERS[index + 1][2] - 1
            if index + 1 < len(EXPECTED_CHAPTERS)
            else page_count
        )
        chapter = Chapter(
            order_no=order_no,
            title=title,
            page_start=start,
            page_end=end,
            anchor=f"sec-{order_no}",
        )
        for block in blocks:
            if not (start <= block.page <= end):
                continue
            first_line = block.text.splitlines()[0] if block.text else ""
            if block.kind == "section":
                match = SECTION_RE.match(first_line)
                if match:
                    chapter.sections.append(
                        Section(
                            ref=match.group(1),
                            title=first_line.strip(),
                            page_start=block.page,
                            page_end=end,
                        )
                    )
            elif block.kind != "chapter":
                if chapter.sections:
                    chapter.sections[-1].blocks.append(block)
                else:
                    chapter.blocks.append(block)
        chapters.append(chapter)
    return chapters


def build_chunks(chapters: list[Chapter], max_chars: int = 800) -> list[Chunk]:
    chunks: list[Chunk] = []
    for chapter in chapters:
        order = 0
        for section in chapter.sections:
            paragraphs = [b for b in section.blocks if b.kind == "paragraph"]
            tables = [b for b in section.blocks if b.kind == "table"]
            buffer: list[TextBlock] = []
            size = 0

            def flush() -> None:
                nonlocal order, buffer, size
                if not buffer:
                    return
                content = "\n\n".join(block.text for block in buffer).strip()
                if not content:
                    buffer, size = [], 0
                    return
                order += 1
                chunks.append(
                    Chunk(
                        chapter_order=chapter.order_no,
                        chapter_title=chapter.title,
                        section_ref=section.ref,
                        section_title=section.title,
                        order_no=order,
                        content=(
                            f"章节：{chapter.title}\n小节：{section.title}\n\n{content}"
                        ),
                        page_start=min(block.page for block in buffer),
                        page_end=max(block.page for block in buffer),
                    )
                )
                buffer, size = [], 0

            for block in paragraphs:
                if size >= 300 and size + len(block.text) > max_chars:
                    flush()
                buffer.append(block)
                size += len(block.text)
            flush()

            for table in tables:
                order += 1
                chunks.append(
                    Chunk(
                        chapter_order=chapter.order_no,
                        chapter_title=chapter.title,
                        section_ref=section.ref,
                        section_title=section.title,
                        order_no=order,
                        content=(
                            f"章节：{chapter.title}\n小节：{section.title}\n\n"
                            f"{table.text}"
                        ),
                        page_start=table.page,
                        page_end=table.page,
                        table_confidence=table.table_confidence,
                    )
                )

        if not chapter.sections:
            content = "\n\n".join(block.text for block in chapter.blocks).strip()
            if content:
                chunks.append(
                    Chunk(
                        chapter_order=chapter.order_no,
                        chapter_title=chapter.title,
                        section_ref=None,
                        section_title=None,
                        order_no=1,
                        content=f"章节：{chapter.title}\n\n{content}",
                        page_start=chapter.page_start,
                        page_end=chapter.page_end,
                    )
                )
    return chunks


def chapter_weight(chapter: Chapter, total_sections: int) -> float:
    return round(len(chapter.sections) / max(1, total_sections), 4)

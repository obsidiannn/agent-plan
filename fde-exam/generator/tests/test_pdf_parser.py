from pathlib import Path

from fde_exam_gen.pdf_parser import build_chunks, parse_pdf

PDF = Path(__file__).resolve().parents[2] / "doc" / "fde.pdf"


def test_pdf_structure(tmp_path):
    parsed = parse_pdf(PDF, image_dir=tmp_path, ignore_pages=(1, 2, 3))
    assert parsed.page_count == 151
    assert len(parsed.chapters) == 12
    starts = [chapter.page_start for chapter in parsed.chapters]
    assert starts == [4, 14, 28, 40, 49, 66, 82, 97, 111, 124, 137, 144]
    assert parsed.chapters[0].title.startswith("01 ")
    assert parsed.chapters[11].title.startswith("12 ")
    assert len(parsed.images) >= 20
    assert parsed.table_count > 100


def test_footer_removed_and_chunks_built():
    parsed = parse_pdf(PDF, image_dir=None, ignore_pages=(1, 2, 3))
    chunks = build_chunks(parsed.chapters)
    assert len(chunks) > 100
    joined = "\n".join(chunk.content for chunk in chunks)
    assert "FDE Course Notes" not in joined
    assert "第 1 页" not in joined
    assert all(chunk.page_start >= 4 for chunk in chunks)
    assert all(chunk.page_end <= 151 for chunk in chunks)

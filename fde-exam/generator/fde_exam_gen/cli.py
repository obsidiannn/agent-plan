from __future__ import annotations

import csv
import json
from pathlib import Path

import typer

from fde_exam_gen.config import load_settings
from fde_exam_gen.demo import seed_demo
from fde_exam_gen.generate import run_generation
from fde_exam_gen.ingest import import_ingest, run_ingest
from fde_exam_gen.repository import Repository

app = typer.Typer(no_args_is_help=True, help="FDE 课程 PDF → 题库生成器")


def _print(data: dict) -> None:
    typer.echo(json.dumps(data, ensure_ascii=False, indent=2))


@app.command()
def ingest(
    db: bool = typer.Option(True, "--db/--no-db", help="解析后是否写入 SQLite"),
):
    """解析 doc/fde.pdf，生成 fde.md / structure.json，并导入数据库。"""
    settings = load_settings()
    result = run_ingest(settings)
    summary = {
        key: result[key]
        for key in (
            "pages",
            "chapters",
            "tables",
            "lowConfidenceTables",
            "images",
            "markdownPath",
            "structurePath",
        )
    }
    summary["chunks"] = len(result["chunks"])
    if db:
        summary["db"] = import_ingest(settings, result)
    _print(summary)


@app.command("seed-demo")
def seed_demo_cmd():
    """从已导入的章节结构生成结构型演示题库（无需 LLM）。"""
    settings = load_settings()
    _print(seed_demo(settings))


@app.command()
def run(
    target: int = typer.Option(150, help="候选题目数量"),
    seed: int = typer.Option(42),
    prompt_version: str = typer.Option("v1"),
    chapter: str | None = typer.Option(None, help="只生成标题包含该字符串的章节"),
    auto_approve: bool = typer.Option(False, "--auto-approve"),
):
    """调用 LLM 正式生成题目（需要 LLM_API_KEY）。"""
    settings = load_settings()
    result = run_generation(
        settings,
        target=target,
        seed=seed,
        prompt_version=prompt_version,
        chapter_filter=chapter,
        auto_approve=auto_approve,
    )
    _print(result)


@app.command()
def stats():
    """查看题库统计和组卷就绪状态。"""
    settings = load_settings()
    repo = Repository(settings.db_path)
    result = repo.stats()
    result["ready"] = (
        result["approvedByType"].get("SINGLE", 0) >= 40
        and result["approvedByType"].get("MULTIPLE", 0) >= 20
    )
    repo.close()
    _print(result)


@app.command()
def scan(threshold: int = typer.Option(4, help="SimHash Hamming 距离阈值")):
    """扫描全库近似重复题目。"""
    settings = load_settings()
    repo = Repository(settings.db_path)
    pairs = repo.list_duplicate_pairs(threshold)
    repo.close()
    typer.echo(f"发现 {len(pairs)} 对相似题（Hamming ≤ {threshold}）")
    for pair in pairs[:30]:
        distance, left_id, left_status, left_stem, right_id, right_status, right_stem = pair
        typer.echo(
            f"- d={distance} [{left_status}] {left_stem[:36]} <> [{right_status}] {right_stem[:36]}"
        )
    if len(pairs) > 30:
        typer.echo(f"... 其余 {len(pairs) - 30} 对略")


@app.command("export-review")
def export_review(
    status: str = typer.Option("PENDING_REVIEW"),
    out: Path = typer.Option(Path("reports/review.csv")),
):
    """导出待审题目 CSV。"""
    settings = load_settings()
    repo = Repository(settings.db_path)
    rows = repo.export_review_csv(status)
    repo.close()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        typer.echo("没有符合条件的题目")
        return
    with out.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    typer.echo(f"已导出 {len(rows)} 条到 {out}")


@app.command("import-review")
def import_review(
    file: Path = typer.Option(..., help="CSV：id,status,note"),
    reviewer: str = typer.Option("admin"),
):
    """从 CSV 导入审核结果（status=APPROVED/REJECTED/DISABLED）。"""
    settings = load_settings()
    repo = Repository(settings.db_path)
    updated = 0
    with file.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if not row.get("id") or not row.get("status"):
                continue
            repo.set_question_status(
                row["id"].strip(),
                row["status"].strip(),
                reviewer,
                row.get("note", "").strip() or None,
            )
            updated += 1
    repo.commit_changes()
    repo.close()
    typer.echo(f"已更新 {updated} 条")


@app.command()
def doctor():
    """检查 PDF、数据文件与数据库是否就绪。"""
    settings = load_settings()
    result = {
        "db": str(settings.db_path),
        "dbExists": settings.db_path.exists(),
        "pdf": str(settings.source_pdf),
        "pdfExists": settings.source_pdf.exists(),
        "markdown": str(settings.source_out_dir / "fde.md"),
        "markdownExists": (settings.source_out_dir / "fde.md").exists(),
        "structure": str(settings.source_out_dir / "fde.structure.json"),
        "structureExists": (settings.source_out_dir / "fde.structure.json").exists(),
        "llmConfigured": bool(settings.llm_api_key),
        "llmBaseUrl": settings.llm_base_url,
        "llmModel": settings.llm_model,
        "llmUserAgent": settings.llm_user_agent,
        "opencodeSession": settings.llm_session
        if "opencode.ai" in settings.llm_base_url
        else None,
    }
    if settings.db_path.exists():
        repo = Repository(settings.db_path)
        result["stats"] = repo.stats()
        repo.close()
    _print(result)


if __name__ == "__main__":
    app()

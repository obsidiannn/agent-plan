from __future__ import annotations

import random

from fde_exam_gen.config import Settings
from fde_exam_gen.dedupe import add_to_index, check_duplicate, prepare_index
from fde_exam_gen.models import GeneratedQuestion, OptionModel
from fde_exam_gen.repository import Repository


def _section_catalog(chapters: list[dict]) -> list[dict]:
    sections: list[dict] = []
    for chapter in chapters:
        seen: set[str] = set()
        for chunk in chapter.get("chunks", []):
            key = chunk.get("sectionRef") or "__chapter__"
            if key in seen:
                continue
            if chunk.get("tableConfidence") == "LOW":
                continue
            seen.add(key)
            content = chunk["content"]
            section_title = chunk.get("sectionRef") or chapter["title"]
            for line in content.splitlines():
                if line.startswith("小节："):
                    section_title = line[3:].strip()
                    break
            sections.append(
                {
                    "chapterId": chapter["id"],
                    "chapterOrder": chapter["orderNo"],
                    "chapterTitle": chapter["title"],
                    "sectionRef": chunk.get("sectionRef"),
                    "sectionTitle": section_title,
                    "chunkId": chunk["id"],
                    "chunkContent": content,
                    "page": chunk.get("pageStart") or chapter.get("pageStart") or 4,
                }
            )
    return sections


def _shuffled_options(correct: list[str], wrong: list[str], seed_text: str):
    rng = random.Random(seed_text)
    options = [("correct", text) for text in correct] + [
        ("wrong", text) for text in wrong
    ]
    rng.shuffle(options)
    keys = "ABCD"
    mapped = []
    answer = []
    for index, (kind, text) in enumerate(options[:4]):
        key = keys[index]
        mapped.append(OptionModel(key=key, content=text))
        if kind == "correct":
            answer.append(key)
    return mapped, answer


def _insert_demo_question(
    repo: Repository,
    *,
    settings: Settings,
    index: dict,
    run_id: str,
    question: GeneratedQuestion,
    chapter_id: str,
    chunk_id: str,
    source_ref: str | None,
    source_page: int,
) -> bool:
    duplicate, fp = check_duplicate(
        repo, settings, index, question, chapter_id
    )
    if duplicate:
        return False
    repo.insert_question_with_candidate(
        question=question,
        run_id=run_id,
        chapter_id=chapter_id,
        source_chunk_id=chunk_id,
        source_ref=source_ref,
        source_page=source_page,
        source_page_end=source_page,
        content_hash=fp["content_hash"],
        claim_hash=fp["claim_hash"],
        simhash_hex=fp["simhash_hex"],
        status="APPROVED",
        prompt_version="demo-v1",
        quality_score=4.0,
        quality_detail={"demo": True, "note": "结构型演示题，可由正式 LLM 生成替换"},
    )
    add_to_index(index, fp)
    return True


def seed_demo(settings: Settings) -> dict:
    repo = Repository(settings.db_path)
    chapters = repo.chapters_with_chunks()
    if not chapters:
        raise RuntimeError("没有章节数据，请先执行 ingest --db")

    source = repo.conn.execute(
        "SELECT contentHash FROM source_docs ORDER BY createdAt DESC LIMIT 1"
    ).fetchone()
    source_hash = source["contentHash"] if source else "demo"

    sections = _section_catalog(chapters)
    if len(sections) < 20:
        raise RuntimeError("章节小节数量不足，无法生成演示题库")

    total_planned = len(sections) + len(chapters) * 2
    run_id = repo.start_run(
        source_hash=source_hash,
        model="demo-structural",
        prompt_version="demo-v1",
        seed=42,
        target_count=total_planned,
    )
    index = prepare_index(repo)
    accepted = 0
    generated = 0

    by_chapter: dict[str, list[dict]] = {}
    for section in sections:
        by_chapter.setdefault(section["chapterId"], []).append(section)

    # 单选：每个小节一道“所属章节”题；覆盖全部 12 章。
    for position, section in enumerate(sections):
        generated += 1
        other_titles = [
            item["sectionTitle"]
            for item in sections
            if item["chapterId"] != section["chapterId"]
        ]
        rng = random.Random(f"single-{position}-{section['sectionTitle']}")
        wrong = rng.sample(other_titles, 3)
        options, answer = _shuffled_options(
            [section["sectionTitle"]],
            wrong,
            f"single-options-{position}",
        )
        question = GeneratedQuestion(
            type="SINGLE",
            stem=f"以下哪一项属于第 {section['chapterOrder']} 章《{section['chapterTitle']}》的小节？",
            options=options,
            answer=answer,
            explanation=(
                f"“{section['sectionTitle']}”位于第 {section['chapterOrder']} 章"
                f"《{section['chapterTitle']}》，PDF 第 {section['page']} 页。"
            ),
            evidence_quote=f"小节：{section['sectionTitle']}",
            source_page=int(section["page"]),
            claim=(
                f"小节「{section['sectionTitle']}」属于第 {section['chapterOrder']} 章"
                f"「{section['chapterTitle']}」"
            ),
            knowledge_point=section["sectionTitle"],
            difficulty="EASY",
        )
        if _insert_demo_question(
            repo,
            settings=settings,
            index=index,
            run_id=run_id,
            question=question,
            chapter_id=section["chapterId"],
            chunk_id=section["chunkId"],
            source_ref=section["sectionRef"],
            source_page=int(section["page"]),
        ):
            accepted += 1

    # 多选：每章两题，考查“本章包含哪些小节”，凑足 20+ 道。
    templates = [
        "以下哪些小节属于第 {order} 章《{title}》？",
        "根据课程目录，第 {order} 章《{title}》包含以下哪些小节？",
        "在 FDE 课程中，下列哪些内容属于第 {order} 章《{title}》？",
        "第 {order} 章《{title}》的教学内容包含以下哪些小节？",
        "下列选项中，哪些是第 {order} 章《{title}》的小节？",
    ]
    template_index = 0
    for chapter in chapters:
        chapter_sections = by_chapter.get(chapter["id"], [])
        if len(chapter_sections) < 3:
            continue
        candidates: list[list[dict]] = []
        candidates.append(chapter_sections[:3])
        if len(chapter_sections) >= 4:
            candidates.append(chapter_sections[-3:])
        for subset in candidates[:2]:
            if len(subset) < 3:
                continue
            generated += 1
            first = subset[0]
            distractor_pool = [
                item
                for item in sections
                if item["chapterId"] != chapter["id"]
            ]
            rng = random.Random(f"multi-{chapter['orderNo']}-{first['sectionTitle']}")
            distractor = rng.choice(distractor_pool)
            correct_titles = [item["sectionTitle"] for item in subset]
            options, answer = _shuffled_options(
                correct_titles,
                [distractor["sectionTitle"]],
                f"multi-options-{chapter['orderNo']}-{first['sectionTitle']}",
            )
            template = templates[template_index % len(templates)]
            template_index += 1
            refs = "、".join(item["sectionRef"] or item["sectionTitle"] for item in subset)
            question = GeneratedQuestion(
                type="MULTIPLE",
                stem=template.format(
                    order=chapter["orderNo"], title=chapter["title"]
                ),
                options=options,
                answer=answer,
                explanation=(
                    f"第 {chapter['orderNo']} 章《{chapter['title']}》包含的小节包括："
                    f"{correct_titles[0]}、{correct_titles[1]}、{correct_titles[2]}。"
                ),
                evidence_quote=first["chunkContent"][:120],
                source_page=int(first["page"]),
                claim=(
                    f"第 {chapter['orderNo']} 章「{chapter['title']}」包含小节 {refs}"
                ),
                knowledge_point=f"第 {chapter['orderNo']} 章目录结构",
                difficulty="MEDIUM",
            )
            if _insert_demo_question(
                repo,
                settings=settings,
                index=index,
                run_id=run_id,
                question=question,
                chapter_id=chapter["id"],
                chunk_id=first["chunkId"],
                source_ref=first["sectionRef"],
                source_page=int(first["page"]),
            ):
                accepted += 1

    repo.update_run(
        run_id,
        generated=generated,
        accepted=accepted,
        rejected=generated - accepted,
        status="SUCCESS",
    )
    stats = repo.stats()
    repo.close()
    return {
        "runId": run_id,
        "generated": generated,
        "accepted": accepted,
        "stats": stats,
    }

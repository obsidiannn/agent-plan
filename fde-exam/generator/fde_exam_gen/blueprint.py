from __future__ import annotations

import math

SINGLE_STYLES = [
    "SCENARIO",
    "TROUBLESHOOTING",
    "COMPARISON",
    "PROCESS",
    "CALCULATION",
    "JUDGMENT",
]
MULTIPLE_STYLES = ["JUDGMENT", "JUDGMENT", "COMPARISON", "PROCESS"]


def _largest_remainder(total: int, weights: list[float]) -> list[int]:
    if not weights:
        return []
    weight_sum = sum(weights) or len(weights)
    raw = [total * (weight / weight_sum) for weight in weights]
    base = [int(value) for value in raw]
    remainder = total - sum(base)
    order = sorted(
        range(len(weights)),
        key=lambda index: (raw[index] - base[index], weights[index]),
        reverse=True,
    )
    for index in order[:remainder]:
        base[index] += 1
    return base


def _split_by_sections(total: int, count: int) -> list[int]:
    if count <= 0:
        return []
    base = total // count
    extra = total % count
    return [base + (1 if index < extra else 0) for index in range(count)]


def build_units(
    chapters: list[dict],
    target: int,
    single_style_override: str | None = None,
    multiple_style_override: str | None = None,
) -> list[dict]:
    single_total = math.ceil(target * 2 / 3)
    multiple_total = target - single_total
    weights = [max(0.01, float(chapter.get("weight") or 1)) for chapter in chapters]
    single_quotas = _largest_remainder(single_total, weights)
    multiple_quotas = _largest_remainder(multiple_total, weights)

    units: list[dict] = []
    style_index = 0
    for index, chapter in enumerate(chapters):
        chunks = chapter.get("chunks") or []
        if not chunks:
            continue
        sections: dict[str, dict] = {}
        for chunk in chunks:
            key = chunk.get("sectionRef") or "__chapter__"
            current = sections.get(key)
            if current is None or len(chunk.get("content", "")) > len(
                current.get("content", "")
            ):
                sections[key] = chunk
        section_chunks = list(sections.values())
        if not section_chunks:
            continue

        single_parts = _split_by_sections(single_quotas[index], len(section_chunks))
        multi_parts = _split_by_sections(multiple_quotas[index], len(section_chunks))
        for s_index, chunk in enumerate(section_chunks):
            n_single = single_parts[s_index] if s_index < len(single_parts) else 0
            n_multiple = multi_parts[s_index] if s_index < len(multi_parts) else 0
            if n_single == 0 and n_multiple == 0:
                continue
            units.append(
                {
                    "chapterId": chapter["id"],
                    "chapterOrder": chapter["orderNo"],
                    "chapterTitle": chapter["title"],
                    "sectionRef": chunk.get("sectionRef"),
                    "sectionTitle": (chunk.get("sectionRef") or chapter["title"]),
                    "chunkId": chunk["id"],
                    "chunkContent": chunk["content"],
                    "pageStart": chunk.get("pageStart") or chapter.get("pageStart"),
                    "pageEnd": chunk.get("pageEnd") or chapter.get("pageEnd"),
                    "nSingle": n_single,
                    "nMultiple": n_multiple,
                    "singleStyle": single_style_override
                    or SINGLE_STYLES[style_index % len(SINGLE_STYLES)],
                    "multipleStyle": multiple_style_override
                    or MULTIPLE_STYLES[style_index % len(MULTIPLE_STYLES)],
                }
            )
            style_index += 1
    return units

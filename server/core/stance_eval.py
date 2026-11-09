# coding: utf-8
"""立场判定评测: 抽样生成标注模板 + 计算准确率/混淆矩阵

先度量再优化 —— 用人工标注的小样本集衡量 stance 模块的真实准确率,
否则无法判断任何改动是变好还是变差。

用法:
    # 1) 从向量库随机抽样, 生成待标注的 JSONL(label 留空待填)
    uv run python -m server.core.stance_eval sample -n 200 -o stance_eval.jsonl

    # 2) 人工把每行 label 填成 积极/消极/中性 后, 重新判定并算指标
    uv run python -m server.core.stance_eval score -f stance_eval.jsonl
"""
from __future__ import annotations

import argparse
import json
import random

from server.core import claw_graph
from server.core.stance import STANCES, build_text, get_stance


def cmd_sample(args: argparse.Namespace) -> int:
    """从向量库抽样, 写出待人工标注的模板(不预填模型预测, 避免标注被锚定)"""
    collection = claw_graph._get_collection()
    metas = (collection.get(include=["metadatas"]).get("metadatas")) or []
    if not metas:
        print("向量库为空, 无样本可抽。请先采集数据。")
        return 1
    picked = random.sample(metas, min(args.n, len(metas)))
    with open(args.out, "w", encoding="utf-8") as fp:
        for meta in picked:
            fp.write(json.dumps({
                "url": meta.get("url", ""),
                "title": meta.get("title", ""),
                "content": meta.get("content", ""),
                "label": "",  # 人工填写: 积极 / 消极 / 中性 (留空则跳过)
            }, ensure_ascii=False) + "\n")
    print(f"已写出 {len(picked)} 条待标注样本 -> {args.out}")
    print(f"把每行 label 填成 {'/'.join(STANCES)}, 再运行 score 子命令")
    return 0


def _metrics(golds: list[str], preds: list[str]) -> tuple[dict, float, list]:
    """返回 (混淆矩阵, 准确率, 各类 [类别, precision, recall, f1, support])"""
    matrix = {g: {p: 0 for p in STANCES} for g in STANCES}
    for gold, pred in zip(golds, preds):
        matrix[gold][pred] += 1
    total = len(golds)
    rows = []
    for stance in STANCES:
        tp = matrix[stance][stance]
        fp = sum(matrix[g][stance] for g in STANCES if g != stance)
        fn = sum(matrix[stance][p] for p in STANCES if p != stance)
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        f1 = (2 * precision * recall / (precision + recall)
              if precision + recall else 0.0)
        rows.append((stance, precision, recall, f1, tp + fn))
    accuracy = (sum(matrix[s][s] for s in STANCES) / total) if total else 0.0
    return matrix, accuracy, rows


def cmd_score(args: argparse.Namespace) -> int:
    """用当前 stance 实现重新判定已标注样本, 输出准确率与混淆矩阵"""
    records = []
    with open(args.file, encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                records.append(json.loads(line))
    labeled = [r for r in records if r.get("label") in STANCES]
    if not labeled:
        print(f"没有已标注样本(label 需为 {'/'.join(STANCES)})。")
        return 1

    texts = [build_text(r.get("title", ""), r.get("content", ""))
             for r in labeled]
    preds = [res["stance"] for res in get_stance().classify(texts)]
    golds = [r["label"] for r in labeled]

    matrix, accuracy, rows = _metrics(golds, preds)
    macro_f1 = sum(row[3] for row in rows) / len(rows)

    print(f"\n样本 {len(labeled)} 条 (文件共 {len(records)} 行)")
    print(f"准确率 {accuracy:.4f}    宏平均 F1 {macro_f1:.4f}\n")

    print("混淆矩阵(行=人工标注, 列=模型预测)")
    print("      " + "".join(s.rjust(8) for s in STANCES))
    for gold in STANCES:
        print(gold.rjust(4) + "  "
              + "".join(str(matrix[gold][p]).rjust(8) for p in STANCES))

    print("\n" + "类别".ljust(6) + "precision".rjust(11)
          + "recall".rjust(9) + "f1".rjust(9) + "support".rjust(9))
    for stance, precision, recall, f1, support in rows:
        print(stance.ljust(6) + f"{precision:.3f}".rjust(11)
              + f"{recall:.3f}".rjust(9) + f"{f1:.3f}".rjust(9)
              + str(support).rjust(9))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="立场判定评测")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sample = sub.add_parser("sample", help="从向量库抽样生成待标注模板")
    sample.add_argument("-n", type=int, default=200, help="抽样条数")
    sample.add_argument("-o", "--out", default="stance_eval.jsonl",
                        help="输出的标注模板文件")
    sample.set_defaults(func=cmd_sample)

    score = sub.add_parser("score", help="读取标注文件并计算指标")
    score.add_argument("-f", "--file", default="stance_eval.jsonl",
                       help="已标注的 JSONL 文件")
    score.set_defaults(func=cmd_score)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

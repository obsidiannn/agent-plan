import { describe, expect, it } from "vitest";
import { composePaper, mulberry32, seedFromString, type PoolQuestion } from "@/lib/paper";

function makeQuestion(index: number, type: "SINGLE" | "MULTIPLE"): PoolQuestion {
  const chapter = index % 12;
  const correct = type === "SINGLE" ? ["B"] : ["A", "C"];
  return {
    id: `${type}-${index}`,
    type,
    stem: `题目 ${index} 的题干内容`,
    optionsJson: JSON.stringify([
      { key: "A", content: `选项 A ${index}` },
      { key: "B", content: `选项 B ${index}` },
      { key: "C", content: `选项 C ${index}` },
      { key: "D", content: `选项 D ${index}` },
    ]),
    answerJson: JSON.stringify(correct),
    explanation: "解析内容足够长，用于测试。",
    difficulty: "MEDIUM",
    chapterId: `ch-${chapter}`,
    knowledgePoint: "知识点",
    evidenceQuote: "证据",
    sourcePage: 4,
    chapter: { id: `ch-${chapter}`, title: `第 ${chapter} 章`, orderNo: chapter },
  };
}

function pool() {
  return [
    ...Array.from({ length: 60 }, (_, i) => makeQuestion(i, "SINGLE")),
    ...Array.from({ length: 30 }, (_, i) => makeQuestion(i, "MULTIPLE")),
  ];
}

describe("paper composition", () => {
  it("creates 40 single + 20 multiple, 60 items and 100 points", () => {
    const paper = composePaper(pool(), "seed-1");
    expect(paper).toHaveLength(60);
    expect(paper.filter((item) => item.type === "SINGLE")).toHaveLength(40);
    expect(paper.filter((item) => item.type === "MULTIPLE")).toHaveLength(20);
    expect(paper.reduce((sum, item) => sum + item.maxScore, 0)).toBe(100);
    expect(paper.map((item) => item.orderNo)).toEqual(
      Array.from({ length: 60 }, (_, i) => i + 1),
    );
  });

  it("keeps the correct answer after shuffling options", () => {
    const paper = composePaper(pool(), "seed-2");
    for (const item of paper) {
      const options = item.options;
      const answerTexts = options
        .filter((option) => item.answer.includes(option.key))
        .map((option) => option.content);
      if (item.type === "SINGLE") {
        expect(answerTexts).toHaveLength(1);
        expect(answerTexts[0]).toContain("选项 B");
      } else {
        expect(answerTexts).toHaveLength(2);
        expect(answerTexts.some((text) => text.includes("选项 A"))).toBe(true);
        expect(answerTexts.some((text) => text.includes("选项 C"))).toBe(true);
      }
    }
  });

  it("is reproducible with the same seed", () => {
    const first = composePaper(pool(), "fixed-seed").map((item) => ({
      id: item.questionId,
      options: item.options.map((o) => o.content),
      answer: item.answer,
    }));
    const second = composePaper(pool(), "fixed-seed").map((item) => ({
      id: item.questionId,
      options: item.options.map((o) => o.content),
      answer: item.answer,
    }));
    expect(first).toEqual(second);
  });

  it("fails when the pool is too small", () => {
    expect(() => composePaper(pool().slice(0, 50), "seed")).toThrow(
      /题池不足|单选题不足|多选题不足/,
    );
  });

  it("provides deterministic rng helpers", () => {
    const a = mulberry32(seedFromString("abc"));
    const b = mulberry32(seedFromString("abc"));
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });
});

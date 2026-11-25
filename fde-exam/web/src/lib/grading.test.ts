import { describe, expect, it } from "vitest";
import { gradeItem, isSameAnswer, summarize } from "@/lib/grading";

describe("grading", () => {
  it("scores single choice exactly", () => {
    expect(
      gradeItem({ type: "SINGLE", selected: ["B"], correct: ["B"], maxScore: 1.5 }),
    ).toEqual({ isCorrect: true, score: 1.5 });
    expect(
      gradeItem({ type: "SINGLE", selected: ["A"], correct: ["B"], maxScore: 1.5 }),
    ).toEqual({ isCorrect: false, score: 0 });
    expect(
      gradeItem({ type: "SINGLE", selected: [], correct: ["B"], maxScore: 1.5 }),
    ).toEqual({ isCorrect: false, score: 0 });
  });

  it("scores multiple choice all-or-nothing by default", () => {
    expect(
      gradeItem({
        type: "MULTIPLE",
        selected: ["A", "C"],
        correct: ["C", "A"],
        maxScore: 2,
      }),
    ).toEqual({ isCorrect: true, score: 2 });
    expect(
      gradeItem({
        type: "MULTIPLE",
        selected: ["A"],
        correct: ["A", "C"],
        maxScore: 2,
      }),
    ).toEqual({ isCorrect: false, score: 0 });
    expect(
      gradeItem({
        type: "MULTIPLE",
        selected: ["A", "B", "C"],
        correct: ["A", "C"],
        maxScore: 2,
      }),
    ).toEqual({ isCorrect: false, score: 0 });
  });

  it("normalizes answer sets", () => {
    expect(isSameAnswer(["B", "A", "A"], ["A", "B"])).toBe(true);
    expect(isSameAnswer(["A"], ["A", "B"])).toBe(false);
  });

  it("applies the 70 point pass line", () => {
    const passed = summarize([
      { score: 70, isCorrect: true, maxScore: 70 },
      { score: 0, isCorrect: false, maxScore: 30 },
    ]);
    expect(passed.passed).toBe(true);
    const failed = summarize([
      { score: 69.5, isCorrect: true, maxScore: 69.5 },
      { score: 0, isCorrect: false, maxScore: 30.5 },
    ]);
    expect(failed.passed).toBe(false);
  });
});

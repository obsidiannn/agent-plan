import { examConfig } from "@/lib/config";

export function normalizeAnswer(answer: string[] | null | undefined): string[] {
  if (!answer) return [];
  return [...new Set(answer.filter(Boolean))].sort();
}

export function isSameAnswer(a: string[], b: string[]) {
  const left = normalizeAnswer(a);
  const right = normalizeAnswer(b);
  if (left.length !== right.length) return false;
  return left.every((value, index) => value === right[index]);
}

export function gradeItem(params: {
  type: string;
  selected: string[] | null | undefined;
  correct: string[];
  maxScore: number;
}): { isCorrect: boolean; score: number } {
  const selected = normalizeAnswer(params.selected);
  const correct = normalizeAnswer(params.correct);

  if (selected.length === 0) return { isCorrect: false, score: 0 };

  if (params.type === "SINGLE") {
    const isCorrect =
      selected.length === 1 && correct.length === 1 && selected[0] === correct[0];
    return { isCorrect, score: isCorrect ? params.maxScore : 0 };
  }

  const allCorrect =
    selected.length === correct.length &&
    selected.every((value) => correct.includes(value));
  if (allCorrect) return { isCorrect: true, score: params.maxScore };

  if (
    examConfig.multiplePartialCredit &&
    selected.every((value) => correct.includes(value)) &&
    selected.length < correct.length
  ) {
    return {
      isCorrect: false,
      score: Number((params.maxScore / 2).toFixed(2)),
    };
  }
  return { isCorrect: false, score: 0 };
}

export function summarize(
  results: Array<{ score: number; isCorrect: boolean; maxScore: number }>,
) {
  const score = Number(
    results.reduce((sum, item) => sum + item.score, 0).toFixed(2),
  );
  const correctCount = results.filter((item) => item.isCorrect).length;
  const totalScore = results.reduce((sum, item) => sum + item.maxScore, 0);
  return {
    score,
    correctCount,
    totalScore,
    passed: score >= examConfig.passScore,
  };
}

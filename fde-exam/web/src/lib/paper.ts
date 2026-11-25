import { examConfig } from "@/lib/config";
import { PoolInsufficientError } from "@/lib/errors";
import { Option, parseAnswer, parseOptions } from "@/lib/json";

export type PoolQuestion = {
  id: string;
  type: string;
  stem: string;
  optionsJson: string;
  answerJson: string;
  explanation: string;
  difficulty: string;
  chapterId: string | null;
  knowledgePoint: string | null;
  evidenceQuote: string | null;
  sourcePage: number | null;
  chapter: { id: string; title: string; orderNo: number } | null;
};

export type PaperSnapshot = {
  questionId: string;
  orderNo: number;
  type: string;
  stem: string;
  options: Option[];
  answer: string[];
  explanation: string;
  chapterTitle: string | null;
  knowledgePoint: string | null;
  evidenceQuote: string | null;
  sourcePage: number | null;
  maxScore: number;
};

export function seedFromString(input: string): number {
  let h = 2166136261;
  for (let i = 0; i < input.length; i += 1) {
    h ^= input.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a += 0x6d2b79f5;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function shuffle<T>(items: T[], rng: () => number): T[] {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rng() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function pickWithChapterCoverage(
  questions: PoolQuestion[],
  count: number,
  rng: () => number,
): PoolQuestion[] {
  const byChapter = new Map<string, PoolQuestion[]>();
  for (const q of questions) {
    const key = q.chapterId || "unknown";
    const list = byChapter.get(key) || [];
    list.push(q);
    byChapter.set(key, list);
  }

  const selected: PoolQuestion[] = [];
  const selectedIds = new Set<string>();

  const chapterKeys = shuffle([...byChapter.keys()], rng);
  for (const key of chapterKeys) {
    if (selected.length >= count) break;
    const list = shuffle(byChapter.get(key) || [], rng);
    if (list[0]) {
      selected.push(list[0]);
      selectedIds.add(list[0].id);
    }
  }

  const remaining = shuffle(
    questions.filter((q) => !selectedIds.has(q.id)),
    rng,
  );
  for (const q of remaining) {
    if (selected.length >= count) break;
    selected.push(q);
  }

  if (selected.length < count) {
    throw new PoolInsufficientError(
      `题池不足：需要 ${count} 道题，当前可用 ${selected.length} 道`,
    );
  }
  return selected;
}

function remapOptions(question: PoolQuestion, rng: () => number) {
  const options = parseOptions(question.optionsJson);
  if (options.length < 2) {
    throw new Error(`题目 ${question.id} 选项数据异常`);
  }
  const answer = parseAnswer(question.answerJson);
  const answerContents = new Set(
    options.filter((o) => answer.includes(o.key)).map((o) => o.content),
  );
  const shuffled = shuffle(options, rng);
  const keys = "ABCDEF".split("");
  const remapped = shuffled.map((option, index) => ({
    key: keys[index],
    content: option.content,
  }));
  const remappedAnswer = remapped
    .filter((option) => answerContents.has(option.content))
    .map((option) => option.key)
    .sort();
  return { options: remapped, answer: remappedAnswer };
}

export function composePaper(
  pool: PoolQuestion[],
  paperSeed: string,
): PaperSnapshot[] {
  if (
    examConfig.singleCount * examConfig.singleScore +
      examConfig.multipleCount * examConfig.multipleScore !==
    examConfig.totalScore
  ) {
    throw new Error("考试分值配置与满分不一致");
  }

  const singles = pool.filter((q) => q.type === "SINGLE");
  const multiples = pool.filter((q) => q.type === "MULTIPLE");
  if (singles.length < examConfig.singleCount) {
    throw new PoolInsufficientError(
      `单选题不足：需要 ${examConfig.singleCount} 道，当前可用 ${singles.length} 道`,
    );
  }
  if (multiples.length < examConfig.multipleCount) {
    throw new PoolInsufficientError(
      `多选题不足：需要 ${examConfig.multipleCount} 道，当前可用 ${multiples.length} 道`,
    );
  }

  const rng = mulberry32(seedFromString(paperSeed));
  const selected = [
    ...pickWithChapterCoverage(singles, examConfig.singleCount, rng),
    ...pickWithChapterCoverage(multiples, examConfig.multipleCount, rng),
  ];

  const ordered = shuffle(selected, rng);
  return ordered.map((question, index) => {
    const { options, answer } = remapOptions(question, rng);
    const maxScore =
      question.type === "SINGLE"
        ? examConfig.singleScore
        : examConfig.multipleScore;
    return {
      questionId: question.id,
      orderNo: index + 1,
      type: question.type,
      stem: question.stem,
      options,
      answer,
      explanation: question.explanation,
      chapterTitle: question.chapter?.title || null,
      knowledgePoint: question.knowledgePoint,
      evidenceQuote: question.evidenceQuote,
      sourcePage: question.sourcePage,
      maxScore,
    };
  });
}

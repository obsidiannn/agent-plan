import { randomUUID } from "node:crypto";
import { examConfig } from "@/lib/config";
import { prisma } from "@/lib/db";
import { ApiError } from "@/lib/errors";
import { parseAnswer, parseOptions } from "@/lib/json";
import { composePaper, type PoolQuestion } from "@/lib/paper";
import { gradeItem, summarize } from "@/lib/grading";

type SubmitType = "MANUAL" | "TIMEOUT" | "FORCED";

function remainingSeconds(expiresAt: Date | null): number {
  if (!expiresAt) return 0;
  return Math.max(0, Math.floor((expiresAt.getTime() - Date.now()) / 1000));
}

function summaryOf(attempt: {
  id: string;
  score: number | null;
  passed: boolean | null;
  correctCount: number | null;
  totalScore: number;
  submittedAt: Date | null;
  submitType: string | null;
}) {
  return {
    attemptId: attempt.id,
    score: attempt.score ?? 0,
    passed: attempt.passed ?? false,
    correctCount: attempt.correctCount ?? 0,
    totalScore: attempt.totalScore,
    submittedAt: attempt.submittedAt,
    submitType: attempt.submitType,
  };
}

export async function gradeAndSubmitAttempt(params: {
  attemptId: string;
  userId?: string;
  allowAdmin?: boolean;
  submitType?: SubmitType;
}) {
  const { attemptId, userId, allowAdmin = false, submitType = "MANUAL" } = params;

  return prisma.$transaction(async (tx) => {
    const attempt = await tx.examAttempt.findUnique({
      where: { id: attemptId },
      include: { items: { orderBy: { orderNo: "asc" } } },
    });
    if (!attempt) throw new ApiError("NOT_FOUND", "试卷不存在", 404);
    if (userId && attempt.userId !== userId && !allowAdmin) {
      throw new ApiError("FORBIDDEN", "无权访问该试卷", 403);
    }

    if (attempt.status === "SUBMITTED") {
      return summaryOf(attempt);
    }

    const now = new Date();
    const effectiveSubmitType: SubmitType =
      attempt.expiresAt && attempt.expiresAt.getTime() <= now.getTime()
        ? "TIMEOUT"
        : submitType;

    const results: Array<{ score: number; isCorrect: boolean; maxScore: number }> =
      [];

    for (const item of attempt.items) {
      const selected = parseAnswer(item.userAnswerJson);
      const correct = parseAnswer(item.answerJson);
      const result = gradeItem({
        type: item.type,
        selected,
        correct,
        maxScore: item.maxScore,
      });
      results.push({ ...result, maxScore: item.maxScore });
      await tx.attemptQuestion.update({
        where: { id: item.id },
        data: { isCorrect: result.isCorrect, score: result.score },
      });
    }

    const summary = summarize(results);
    const durationSeconds = Math.max(
      0,
      Math.floor((now.getTime() - attempt.startedAt.getTime()) / 1000),
    );

    const updated = await tx.examAttempt.update({
      where: { id: attemptId },
      data: {
        status: "SUBMITTED",
        submitType: effectiveSubmitType,
        activeAttemptKey: null,
        submittedAt: now,
        durationSeconds,
        score: summary.score,
        passed: summary.passed,
        correctCount: summary.correctCount,
      },
    });

    return summaryOf(updated);
  });
}

export async function finalizeExpiredAttempts(userId: string) {
  const now = new Date();
  const expired = await prisma.examAttempt.findMany({
    where: {
      userId,
      status: "IN_PROGRESS",
      expiresAt: { lte: now },
    },
    select: { id: true },
  });
  for (const attempt of expired) {
    await gradeAndSubmitAttempt({
      attemptId: attempt.id,
      userId,
      submitType: "TIMEOUT",
    });
  }
}

export async function getOrCreateAttempt(userId: string) {
  await finalizeExpiredAttempts(userId);

  const existing = await prisma.examAttempt.findFirst({
    where: { userId, status: "IN_PROGRESS" },
    orderBy: { startedAt: "desc" },
  });
  if (existing) {
    return {
      attemptId: existing.id,
      resumed: true,
      remainingSeconds: remainingSeconds(existing.expiresAt),
    };
  }

  const pool = (await prisma.question.findMany({
    where: { status: "APPROVED" },
    include: {
      chapter: { select: { id: true, title: true, orderNo: true } },
    },
  })) as PoolQuestion[];

  const paperSeed = randomUUID();
  const snapshots = composePaper(pool, paperSeed);
  const expiresAt = new Date(
    Date.now() + examConfig.durationMinutes * 60 * 1000,
  );

  try {
    const attempt = await prisma.examAttempt.create({
      data: {
        userId,
        status: "IN_PROGRESS",
        activeAttemptKey: userId,
        paperSeed,
        questionCount: snapshots.length,
        singleCount: examConfig.singleCount,
        multipleCount: examConfig.multipleCount,
        totalScore: examConfig.totalScore,
        expiresAt,
        items: {
          create: snapshots.map((item) => ({
            questionId: item.questionId,
            orderNo: item.orderNo,
            type: item.type,
            stem: item.stem,
            optionsJson: JSON.stringify(item.options),
            answerJson: JSON.stringify(item.answer),
            explanation: item.explanation,
            chapterTitle: item.chapterTitle,
            knowledgePoint: item.knowledgePoint,
            evidenceQuote: item.evidenceQuote,
            sourcePage: item.sourcePage,
            maxScore: item.maxScore,
          })),
        },
      },
    });
    return {
      attemptId: attempt.id,
      resumed: false,
      remainingSeconds: remainingSeconds(attempt.expiresAt),
    };
  } catch (error) {
    const code = (error as { code?: string }).code;
    if (code === "P2002") {
      const active = await prisma.examAttempt.findFirst({
        where: { userId, status: "IN_PROGRESS" },
      });
      if (active) {
        return {
          attemptId: active.id,
          resumed: true,
          remainingSeconds: remainingSeconds(active.expiresAt),
        };
      }
    }
    throw error;
  }
}

export async function getCurrentAttempt(userId: string) {
  await finalizeExpiredAttempts(userId);
  const attempt = await prisma.examAttempt.findFirst({
    where: { userId, status: "IN_PROGRESS" },
    orderBy: { startedAt: "desc" },
  });
  if (!attempt) return null;
  return {
    attemptId: attempt.id,
    startedAt: attempt.startedAt,
    expiresAt: attempt.expiresAt,
    remainingSeconds: remainingSeconds(attempt.expiresAt),
    questionCount: attempt.questionCount,
  };
}

export async function getExamPayload(attemptId: string, userId: string) {
  const attempt = await prisma.examAttempt.findUnique({
    where: { id: attemptId },
    include: { items: { orderBy: { orderNo: "asc" } } },
  });
  if (!attempt) throw new ApiError("NOT_FOUND", "试卷不存在", 404);
  if (attempt.userId !== userId) {
    throw new ApiError("FORBIDDEN", "无权访问该试卷", 403);
  }

  if (attempt.status === "IN_PROGRESS" && attempt.expiresAt && attempt.expiresAt.getTime() <= Date.now()) {
    await gradeAndSubmitAttempt({
      attemptId,
      userId,
      submitType: "TIMEOUT",
    });
    throw new ApiError("ATTEMPT_EXPIRED", "考试已超时并自动交卷", 409, {
      attemptId,
    });
  }

  if (attempt.status === "SUBMITTED") {
    throw new ApiError("CONFLICT", "试卷已交卷", 409, { attemptId });
  }

  return {
    attempt: {
      id: attempt.id,
      startedAt: attempt.startedAt,
      expiresAt: attempt.expiresAt,
      remainingSeconds: remainingSeconds(attempt.expiresAt),
      questionCount: attempt.questionCount,
      totalScore: attempt.totalScore,
    },
    items: attempt.items.map((item) => ({
      orderNo: item.orderNo,
      type: item.type,
      stem: item.stem,
      options: parseOptions(item.optionsJson),
      selected: parseAnswer(item.userAnswerJson),
      maxScore: item.maxScore,
      chapterTitle: item.chapterTitle,
      knowledgePoint: item.knowledgePoint,
    })),
  };
}

export async function saveAnswers(
  attemptId: string,
  userId: string,
  answers: Array<{ orderNo: number; selected: string[] }>,
) {
  const attempt = await prisma.examAttempt.findUnique({
    where: { id: attemptId },
    include: { items: { orderBy: { orderNo: "asc" } } },
  });
  if (!attempt) throw new ApiError("NOT_FOUND", "试卷不存在", 404);
  if (attempt.userId !== userId) {
    throw new ApiError("FORBIDDEN", "无权访问该试卷", 403);
  }
  if (attempt.status !== "IN_PROGRESS") {
    throw new ApiError("CONFLICT", "试卷已交卷", 409, { attemptId });
  }
  if (attempt.expiresAt && attempt.expiresAt.getTime() <= Date.now()) {
    await gradeAndSubmitAttempt({ attemptId, userId, submitType: "TIMEOUT" });
    throw new ApiError("ATTEMPT_EXPIRED", "考试已超时并自动交卷", 409, {
      attemptId,
    });
  }

  const itemByOrder = new Map(attempt.items.map((item) => [item.orderNo, item]));
  const normalized = new Map<number, string[]>();

  for (const answer of answers) {
    const item = itemByOrder.get(answer.orderNo);
    if (!item) {
      throw new ApiError("VALIDATION_ERROR", `题号 ${answer.orderNo} 不存在`, 400);
    }
    const validKeys = new Set(parseOptions(item.optionsJson).map((o) => o.key));
    const selected = [...new Set(answer.selected || [])];
    if (selected.some((key) => !validKeys.has(key))) {
      throw new ApiError("VALIDATION_ERROR", `题号 ${answer.orderNo} 选项非法`, 400);
    }
    if (item.type === "SINGLE" && selected.length > 1) {
      throw new ApiError("VALIDATION_ERROR", `题号 ${answer.orderNo} 是单选题`, 400);
    }
    if (item.type === "MULTIPLE" && selected.length > 6) {
      throw new ApiError("VALIDATION_ERROR", `题号 ${answer.orderNo} 选项过多`, 400);
    }
    normalized.set(answer.orderNo, selected.sort());
  }

  const now = new Date();
  if (normalized.size > 0) {
    await prisma.$transaction(
      [...normalized.entries()].map(([orderNo, selected]) => {
        const item = itemByOrder.get(orderNo)!;
        return prisma.attemptQuestion.update({
          where: { id: item.id },
          data: {
            userAnswerJson: JSON.stringify(selected),
            answeredAt: selected.length > 0 ? now : null,
          },
        });
      }),
    );
  }

  return {
    savedAt: now,
    remainingSeconds: remainingSeconds(attempt.expiresAt),
  };
}

export async function listRecords(userId: string, page = 1, pageSize = 20) {
  const safePage = Math.max(1, page);
  const safeSize = Math.min(50, Math.max(1, pageSize));
  const where = { userId, status: "SUBMITTED" };
  const [total, items] = await Promise.all([
    prisma.examAttempt.count({ where }),
    prisma.examAttempt.findMany({
      where,
      orderBy: { submittedAt: "desc" },
      skip: (safePage - 1) * safeSize,
      take: safeSize,
      select: {
        id: true,
        startedAt: true,
        submittedAt: true,
        durationSeconds: true,
        score: true,
        totalScore: true,
        passed: true,
        correctCount: true,
        questionCount: true,
        submitType: true,
      },
    }),
  ]);
  return {
    items,
    total,
    page: safePage,
    pageSize: safeSize,
    totalPages: Math.max(1, Math.ceil(total / safeSize)),
  };
}

export async function getRecordDetail(
  attemptId: string,
  viewer: { id: string; role: string },
) {
  const attempt = await prisma.examAttempt.findUnique({
    where: { id: attemptId },
    include: { items: { orderBy: { orderNo: "asc" } } },
  });
  if (!attempt) throw new ApiError("NOT_FOUND", "记录不存在", 404);
  if (attempt.userId !== viewer.id && viewer.role !== "ADMIN") {
    throw new ApiError("FORBIDDEN", "无权查看该记录", 403);
  }
  if (attempt.status !== "SUBMITTED") {
    throw new ApiError("CONFLICT", "试卷尚未交卷", 409, { attemptId });
  }
  return {
    attempt: {
      id: attempt.id,
      startedAt: attempt.startedAt,
      submittedAt: attempt.submittedAt,
      durationSeconds: attempt.durationSeconds,
      score: attempt.score,
      totalScore: attempt.totalScore,
      passed: attempt.passed,
      correctCount: attempt.correctCount,
      questionCount: attempt.questionCount,
      submitType: attempt.submitType,
    },
    items: attempt.items.map((item) => ({
      orderNo: item.orderNo,
      type: item.type,
      stem: item.stem,
      options: parseOptions(item.optionsJson),
      answer: parseAnswer(item.answerJson),
      selected: parseAnswer(item.userAnswerJson),
      explanation: item.explanation,
      chapterTitle: item.chapterTitle,
      knowledgePoint: item.knowledgePoint,
      evidenceQuote: item.evidenceQuote,
      sourcePage: item.sourcePage,
      isCorrect: item.isCorrect,
      score: item.score,
      maxScore: item.maxScore,
    })),
  };
}

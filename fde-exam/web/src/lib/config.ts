function intEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseInt(raw, 10);
  return Number.isFinite(value) ? value : fallback;
}

function floatEnv(name: string, fallback: number): number {
  const raw = process.env[name];
  if (!raw) return fallback;
  const value = Number.parseFloat(raw);
  return Number.isFinite(value) ? value : fallback;
}

function boolEnv(name: string, fallback: boolean): boolean {
  const raw = process.env[name];
  if (!raw) return fallback;
  return raw.toLowerCase() === "true";
}

export const examConfig = {
  questionCount: intEnv("EXAM_QUESTION_COUNT", 60),
  singleCount: intEnv("EXAM_SINGLE_COUNT", 40),
  multipleCount: intEnv("EXAM_MULTIPLE_COUNT", 20),
  singleScore: floatEnv("EXAM_SINGLE_SCORE", 1.5),
  multipleScore: floatEnv("EXAM_MULTIPLE_SCORE", 2),
  totalScore: floatEnv("EXAM_TOTAL_SCORE", 100),
  passScore: floatEnv("EXAM_PASS_SCORE", 70),
  durationMinutes: intEnv("EXAM_DURATION_MINUTES", 90),
  fixedPaper: boolEnv("EXAM_FIXED_PAPER", false),
  multiplePartialCredit: boolEnv("EXAM_MULTIPLE_PARTIAL_CREDIT", false),
};

export const authConfig = {
  cookieName: process.env.AUTH_COOKIE_NAME || "fde_session",
  tokenTtlDays: intEnv("AUTH_TOKEN_TTL_DAYS", 7),
  secret:
    process.env.AUTH_SECRET ||
    "fde-exam-dev-secret-change-me-please-32-bytes",
};

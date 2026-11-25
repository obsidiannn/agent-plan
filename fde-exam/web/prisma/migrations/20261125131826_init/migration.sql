-- CreateTable
CREATE TABLE "users" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "username" TEXT NOT NULL,
    "passwordHash" TEXT NOT NULL,
    "nickname" TEXT,
    "role" TEXT NOT NULL DEFAULT 'USER',
    "status" TEXT NOT NULL DEFAULT 'ACTIVE',
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "source_docs" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "title" TEXT NOT NULL,
    "url" TEXT,
    "format" TEXT NOT NULL DEFAULT 'PDF',
    "filePath" TEXT,
    "fileHash" TEXT,
    "pageCount" INTEGER NOT NULL DEFAULT 0,
    "contentHash" TEXT NOT NULL,
    "wordCount" INTEGER NOT NULL DEFAULT 0,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- CreateTable
CREATE TABLE "chapters" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "docId" TEXT NOT NULL,
    "title" TEXT NOT NULL,
    "orderNo" INTEGER NOT NULL,
    "weight" REAL NOT NULL DEFAULT 1,
    "pageStart" INTEGER,
    "pageEnd" INTEGER,
    "anchor" TEXT,
    CONSTRAINT "chapters_docId_fkey" FOREIGN KEY ("docId") REFERENCES "source_docs" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "source_chunks" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "chapterId" TEXT NOT NULL,
    "orderNo" INTEGER NOT NULL,
    "content" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "tokenCount" INTEGER NOT NULL DEFAULT 0,
    "pageStart" INTEGER,
    "pageEnd" INTEGER,
    "sectionRef" TEXT,
    "tableConfidence" TEXT,
    CONSTRAINT "source_chunks_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "chapters" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "questions" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "type" TEXT NOT NULL,
    "stem" TEXT NOT NULL,
    "optionsJson" TEXT NOT NULL,
    "answerJson" TEXT NOT NULL,
    "explanation" TEXT NOT NULL,
    "difficulty" TEXT NOT NULL DEFAULT 'MEDIUM',
    "chapterId" TEXT,
    "knowledgePoint" TEXT,
    "sourceChunkId" TEXT,
    "evidenceQuote" TEXT,
    "sourceRef" TEXT,
    "sourcePage" INTEGER,
    "sourcePageEnd" INTEGER,
    "contentHash" TEXT NOT NULL,
    "claimHash" TEXT,
    "simhash" TEXT,
    "embeddingJson" TEXT,
    "dedupeMetaJson" TEXT,
    "status" TEXT NOT NULL DEFAULT 'PENDING_REVIEW',
    "rejectReason" TEXT,
    "qualityScore" REAL,
    "qualityDetailJson" TEXT,
    "generationRunId" TEXT,
    "promptVersion" TEXT,
    "version" INTEGER NOT NULL DEFAULT 1,
    "reviewedBy" TEXT,
    "reviewedAt" DATETIME,
    "reviewNote" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "questions_chapterId_fkey" FOREIGN KEY ("chapterId") REFERENCES "chapters" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "questions_sourceChunkId_fkey" FOREIGN KEY ("sourceChunkId") REFERENCES "source_chunks" ("id") ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT "questions_generationRunId_fkey" FOREIGN KEY ("generationRunId") REFERENCES "generation_runs" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "generation_runs" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "sourceHash" TEXT NOT NULL,
    "model" TEXT NOT NULL,
    "promptVersion" TEXT NOT NULL,
    "seed" INTEGER,
    "targetCount" INTEGER NOT NULL,
    "generatedCount" INTEGER NOT NULL DEFAULT 0,
    "acceptedCount" INTEGER NOT NULL DEFAULT 0,
    "rejectedCount" INTEGER NOT NULL DEFAULT 0,
    "status" TEXT NOT NULL DEFAULT 'RUNNING',
    "errorMessage" TEXT,
    "costUsd" REAL,
    "startedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finishedAt" DATETIME
);

-- CreateTable
CREATE TABLE "question_candidates" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "runId" TEXT,
    "type" TEXT NOT NULL,
    "contentHash" TEXT NOT NULL,
    "claimHash" TEXT,
    "simhash" TEXT,
    "embeddingJson" TEXT,
    "status" TEXT NOT NULL,
    "rejectReason" TEXT,
    "questionId" TEXT,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT "question_candidates_runId_fkey" FOREIGN KEY ("runId") REFERENCES "generation_runs" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "exam_attempts" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "userId" TEXT NOT NULL,
    "status" TEXT NOT NULL DEFAULT 'IN_PROGRESS',
    "submitType" TEXT,
    "activeAttemptKey" TEXT,
    "paperSeed" TEXT NOT NULL,
    "questionCount" INTEGER NOT NULL DEFAULT 60,
    "singleCount" INTEGER NOT NULL DEFAULT 40,
    "multipleCount" INTEGER NOT NULL DEFAULT 20,
    "totalScore" REAL NOT NULL DEFAULT 100,
    "startedAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "expiresAt" DATETIME,
    "submittedAt" DATETIME,
    "durationSeconds" INTEGER,
    "score" REAL,
    "passed" BOOLEAN,
    "correctCount" INTEGER,
    "createdAt" DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updatedAt" DATETIME NOT NULL,
    CONSTRAINT "exam_attempts_userId_fkey" FOREIGN KEY ("userId") REFERENCES "users" ("id") ON DELETE CASCADE ON UPDATE CASCADE
);

-- CreateTable
CREATE TABLE "attempt_questions" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "attemptId" TEXT NOT NULL,
    "questionId" TEXT,
    "orderNo" INTEGER NOT NULL,
    "type" TEXT NOT NULL,
    "stem" TEXT NOT NULL,
    "optionsJson" TEXT NOT NULL,
    "answerJson" TEXT NOT NULL,
    "explanation" TEXT,
    "chapterTitle" TEXT,
    "knowledgePoint" TEXT,
    "evidenceQuote" TEXT,
    "sourcePage" INTEGER,
    "userAnswerJson" TEXT,
    "isCorrect" BOOLEAN,
    "score" REAL NOT NULL DEFAULT 0,
    "maxScore" REAL NOT NULL,
    "answeredAt" DATETIME,
    CONSTRAINT "attempt_questions_attemptId_fkey" FOREIGN KEY ("attemptId") REFERENCES "exam_attempts" ("id") ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT "attempt_questions_questionId_fkey" FOREIGN KEY ("questionId") REFERENCES "questions" ("id") ON DELETE SET NULL ON UPDATE CASCADE
);

-- CreateIndex
CREATE UNIQUE INDEX "users_username_key" ON "users"("username");

-- CreateIndex
CREATE UNIQUE INDEX "source_docs_contentHash_key" ON "source_docs"("contentHash");

-- CreateIndex
CREATE INDEX "chapters_pageStart_idx" ON "chapters"("pageStart");

-- CreateIndex
CREATE UNIQUE INDEX "chapters_docId_orderNo_key" ON "chapters"("docId", "orderNo");

-- CreateIndex
CREATE INDEX "source_chunks_contentHash_idx" ON "source_chunks"("contentHash");

-- CreateIndex
CREATE INDEX "source_chunks_pageStart_idx" ON "source_chunks"("pageStart");

-- CreateIndex
CREATE UNIQUE INDEX "source_chunks_chapterId_orderNo_key" ON "source_chunks"("chapterId", "orderNo");

-- CreateIndex
CREATE UNIQUE INDEX "questions_contentHash_key" ON "questions"("contentHash");

-- CreateIndex
CREATE INDEX "questions_status_type_idx" ON "questions"("status", "type");

-- CreateIndex
CREATE INDEX "questions_chapterId_type_idx" ON "questions"("chapterId", "type");

-- CreateIndex
CREATE INDEX "questions_claimHash_idx" ON "questions"("claimHash");

-- CreateIndex
CREATE INDEX "questions_simhash_idx" ON "questions"("simhash");

-- CreateIndex
CREATE INDEX "questions_sourcePage_idx" ON "questions"("sourcePage");

-- CreateIndex
CREATE INDEX "questions_generationRunId_idx" ON "questions"("generationRunId");

-- CreateIndex
CREATE INDEX "generation_runs_status_startedAt_idx" ON "generation_runs"("status", "startedAt");

-- CreateIndex
CREATE UNIQUE INDEX "question_candidates_contentHash_key" ON "question_candidates"("contentHash");

-- CreateIndex
CREATE UNIQUE INDEX "question_candidates_questionId_key" ON "question_candidates"("questionId");

-- CreateIndex
CREATE INDEX "question_candidates_status_createdAt_idx" ON "question_candidates"("status", "createdAt");

-- CreateIndex
CREATE INDEX "question_candidates_claimHash_idx" ON "question_candidates"("claimHash");

-- CreateIndex
CREATE INDEX "question_candidates_simhash_idx" ON "question_candidates"("simhash");

-- CreateIndex
CREATE UNIQUE INDEX "exam_attempts_activeAttemptKey_key" ON "exam_attempts"("activeAttemptKey");

-- CreateIndex
CREATE INDEX "exam_attempts_userId_createdAt_idx" ON "exam_attempts"("userId", "createdAt");

-- CreateIndex
CREATE INDEX "exam_attempts_userId_status_idx" ON "exam_attempts"("userId", "status");

-- CreateIndex
CREATE INDEX "attempt_questions_questionId_idx" ON "attempt_questions"("questionId");

-- CreateIndex
CREATE UNIQUE INDEX "attempt_questions_attemptId_orderNo_key" ON "attempt_questions"("attemptId", "orderNo");

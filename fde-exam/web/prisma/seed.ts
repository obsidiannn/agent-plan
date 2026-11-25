import bcrypt from "bcryptjs";
import { PrismaBetterSqlite3 } from "@prisma/adapter-better-sqlite3";
import { PrismaClient } from "../src/generated/prisma/client";

const adapter = new PrismaBetterSqlite3({
  url: process.env.DATABASE_URL || "file:./prisma/dev.db",
});
const prisma = new PrismaClient({ adapter });

async function upsertUser(params: {
  username: string;
  password: string;
  nickname: string;
  role: "USER" | "ADMIN";
}) {
  const passwordHash = await bcrypt.hash(params.password, 11);
  const user = await prisma.user.upsert({
    where: { username: params.username },
    update: {
      nickname: params.nickname,
      role: params.role,
      status: "ACTIVE",
    },
    create: {
      username: params.username,
      passwordHash,
      nickname: params.nickname,
      role: params.role,
    },
  });
  console.log(`user ready: ${user.username} (${user.role})`);
}

async function main() {
  await upsertUser({
    username: "admin",
    password: "admin123456",
    nickname: "管理员",
    role: "ADMIN",
  });
  await upsertUser({
    username: "demo",
    password: "demo123456",
    nickname: "演示用户",
    role: "USER",
  });

  const [chapters, questions] = await Promise.all([
    prisma.chapter.count(),
    prisma.question.count({ where: { status: "APPROVED" } }),
  ]);
  console.log(`database ready: ${chapters} chapters, ${questions} approved questions`);
}

main()
  .catch((error) => {
    console.error(error);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });

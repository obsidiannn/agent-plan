// stocking 库(用户/权限) 专用的 Prisma CLI 配置
// 用法:
//   npx prisma db push --config prisma.stocking.config.ts
//   npx prisma db pull --config prisma.stocking.config.ts
//   npx prisma generate --schema prisma/stocking.prisma
import "dotenv/config";
import { defineConfig } from "prisma/config";

const {
  STOCKING_DB_USER,
  STOCKING_DB_PASSWORD,
  STOCKING_DB_HOST,
  STOCKING_DB_PORT,
  STOCKING_DB_NAME,
} = process.env;

export default defineConfig({
  schema: "prisma/stocking.prisma",
  migrations: {
    path: "prisma/migrations/stocking",
    seed: "tsx prisma/seed-stocking.ts",
  },
  datasource: {
    url: `mysql://${STOCKING_DB_USER}:${STOCKING_DB_PASSWORD}@${STOCKING_DB_HOST}:${STOCKING_DB_PORT}/${STOCKING_DB_NAME}`,
  },
});

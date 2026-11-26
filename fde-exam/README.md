# FDE 模拟考试系统

基于《腾讯云人工智能前沿部署工程师（FDE）》课程 PDF 的模拟考试系统，包含：

- Next.js + React + Prisma + SQLite 在线答题系统
- 登录 / 注册、自动保存、单活跃试卷、交卷评分、逐题复盘
- 管理端题库审核、生成批次查看
- Python 题库生成器：PDF 解析 → 章节/页码映射 → LLM 命题 → 去重 → 质检 → 入库

## 目录

```text
fde-exam/
├── doc/
│   ├── 答题系统方案设计.md
│   └── fde.pdf
├── data/source/              # ingest 生成的 Markdown / 结构 / 图片
├── web/                      # Next.js 应用
├── generator/                # Python 生成器
├── Makefile
└── README.md
```

## 快速开始

### 1. 安装 Web

```bash
cd fde-exam/web
pnpm install
cp .env.example .env        # 本地已提供 .env
pnpm prisma migrate dev
pnpm prisma:generate
pnpm seed                   # 创建 admin / demo 账号
```

### 2. 解析 PDF 并导入数据库

```bash
cd ../generator
uv sync
uv run fde-gen ingest
```

`ingest` 会：

- 解析 `doc/fde.pdf`（151 页 / 12 章）
- 生成 `data/source/fde.md`
- 生成 `data/source/fde.structure.json`（章节、页码、小节）
- 提取图片到 `data/source/images/`
- 把章节和 291 个分块写入 SQLite

### 3. 生成题库

```bash
cd ../generator
uv run fde-gen run --target 150 --seed 42 --prompt-version v1
```

生成完成后在 `/admin/questions` 审核。只有 `APPROVED` 题目会进入组卷池。

> 旧版 `seed-demo` 会生成“某小节属于哪一章”这类目录题，已从 CLI 移除；可用 `uv run fde-gen purge-demo` 清理历史演示题。
>
> 题库检查：`uv run fde-gen stats`、`uv run fde-gen scan --threshold 4`。

### 4. 启动

```bash
cd fde-exam/web
pnpm dev
```

打开 <http://localhost:3100>。

| 账号 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `admin123456` | 管理员 |
| `demo` | `demo123456` | 普通用户 |

> 首次部署请立即修改默认密码，并替换 `AUTH_SECRET`。

当前示例库：**102 道已审核题**（76 单选 + 26 多选），覆盖 12 章；另有 7 道旧批次待审题。目录/章节归属类题目已全部清理。

## 正式题库生成

生成器兼容两种配置方式，`OPENAI_*` 存在时优先使用。

### 方式 A：普通 OpenAI 兼容接口

```bash
LLM_BASE_URL="https://api.deepseek.com/v1"
LLM_API_KEY="sk-..."
LLM_MODEL="deepseek-chat"
```

### 方式 B：OpenCode Go API Key

```bash
OPENAI_API_KEY="sk-..."
OPENAI_BASE_URL="https://opencode.ai/inference/go/openai/v1"
OPENAI_MODEL="deepseek-v4.1-flash"
# 可选：固定会话 ID，便于 OpenCode 做 prompt 缓存
# OPENCODE_SESSION="fde-exam-generator"
```

生成器会自动：

- 把 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 映射为内部 LLM 配置
- 发送 `x-opencode-session` 与 `User-Agent: fde-exam-generator/0.1`
- 在 OpenCode 地址下默认使用 `deepseek-v4.1-flash`

可先执行 `uv run fde-gen doctor` 确认 `llmBaseUrl` / `llmModel`。

然后：

```bash
cd fde-exam/generator
uv run fde-gen run --target 150 --seed 42 --prompt-version v1
```

生成流程：

1. 按章节/小节构建命题蓝图
2. 按知识点调用 LLM 出题（单选 + 多选）
3. Pydantic + 规则校验（题型、答案、选项、禁用表达）
4. 四层去重（精确 hash / SimHash / claim / 可选向量）
5. 证据溯源与 PDF 页码校验
6. 盲测作答一致性
7. LLM 质量评审
8. 写入 `PENDING_REVIEW`，在 `/admin/questions` 人工审核
9. 通过后才进入组卷池

常用命令：

```bash
uv run fde-gen stats
uv run fde-gen scan --threshold 4
uv run fde-gen export-review
uv run fde-gen import-review --file reports/review.csv
uv run fde-gen run --chapter "03 人工智能工程" --target 30
```

> 如需清理历史演示题，可执行 `uv run fde-gen purge-demo`。

## 出题规则

生成器明确禁止“目录题 / 章节归属题 / 页码题”，例如：

- ❌ 以下哪一项属于第 3 章的小节？
- ❌ 以下哪些小节属于第 5 章？
- ❌ 某小节位于第几页？

必须使用真实工作场景切入，题型风格包括：

| style | 说明 | 示例方向 |
| --- | --- | --- |
| `SCENARIO` | 客户场景 / 选型 / 决策 | 某客户要 ERP 集成，应推荐哪个产品 |
| `TROUBLESHOOTING` | 故障排查 | MCP 一直连不上，正确排查顺序 |
| `COMPARISON` | 方案 / 产品 / 阶段对比 | L2 数据 Demo 与 L1/L3 的区别 |
| `PROCESS` | 流程 / 阶段 / 顺序 | 验收标准应在何时确定 |
| `CALCULATION` | 成本 / 积分 / 数量口径 | WMA 哪些动作消耗积分 |
| `JUDGMENT` | 规则 / 边界 / 正误判断 | 某个说法是否符合原文规则 |

硬性规则：

- 单选：3 个干扰项都要对应常见误解，不能有明显荒谬选项。
- 多选：2～3 个正确项，至少一个错误项是“听起来合理但原文否定”的误区。
- 解析必须逐项说明正确项为什么对、至少两个干扰项错在哪里。
- 同一知识点禁止反复出同一种问法。

相关代码：`generator/fde_exam_gen/llm.py`（Prompt）、`validate.py`（R17–R20）、`blueprint.py`（风格分配）。

## 考试规则

- 每套 60 题：40 道单选（1.5 分）+ 20 道多选（2 分）
- 满分 100，70 分及格
- 多选题默认全对得分；可通过 `EXAM_MULTIPLE_PARTIAL_CREDIT=true` 开启“少选得一半”
- 默认 90 分钟，超时自动交卷
- 同一用户同时只能有一份 `IN_PROGRESS` 试卷
- 组卷时随机抽题、随机打乱选项；题干/答案/解析做快照
- 答题接口不返回答案和解析

## API

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/auth/register` | 注册 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 登出 |
| GET | `/api/auth/me` | 当前用户 |
| POST | `/api/exams/start` | 开始 / 恢复考试 |
| GET | `/api/exams/current` | 当前进行中试卷 |
| GET | `/api/exams/:id` | 获取试卷（无答案） |
| PATCH | `/api/exams/:id/answers` | 保存作答 |
| POST | `/api/exams/:id/submit` | 交卷 |
| GET | `/api/records` | 记录列表 |
| GET | `/api/records/:id` | 记录详情 |
| GET | `/api/admin/questions` | 题目列表 |
| PATCH | `/api/admin/questions/:id` | 审核 / 上下架 |
| GET | `/api/admin/runs` | 生成批次 |
| GET | `/api/admin/stats` | 题库统计 |

## 测试

```bash
# Web 单元测试
cd fde-exam/web && pnpm test

# 生成器测试
cd fde-exam/generator && uv sync --extra dev && uv run pytest -q

# 构建
cd fde-exam/web && pnpm build
```

## 配置

Web 配置见 `web/.env.example`；生成器配置见 `generator/.env.example`。

关键项：

- `EXAM_SINGLE_COUNT` / `EXAM_MULTIPLE_COUNT`：每卷题量
- `EXAM_DURATION_MINUTES`：考试时长
- `EXAM_PASS_SCORE`：及格线
- `EXAM_FIXED_PAPER`：固定试卷模式（默认随机组卷）
- `PDF_EXPECTED_PAGES` / `PDF_EXPECTED_CHAPTERS`：PDF 解析校验
- `DEDUP_*`：去重阈值
- `QUALITY_*`：质检阈值

## 说明与限制

- `doc/fde.pdf` 仅用于内部学习与出题，不对外分发。
- 题库必须通过 LLM 生成；生成器已禁止目录/章节归属题，并强制场景、排查、对比、流程、口径、判断题。
- 当前项目为单机 SQLite 架构，适合内部培训/小团队；如要多实例部署，请迁移到 PostgreSQL 并补充共享 session/限流。
- 管理端目前支持审核、上下架、批次查看；题目在线编辑可作为后续增强。

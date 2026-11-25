.PHONY: install dev build test ingest seed-demo stats

install:
	cd web && pnpm install
	cd generator && uv sync --extra dev

migrate:
	cd web && pnpm prisma migrate dev

seed:
	cd web && pnpm seed

dev:
	cd web && pnpm dev

build:
	cd web && pnpm build

test:
	cd web && pnpm test
	cd generator && uv run pytest -q

ingest:
	cd generator && uv run fde-gen ingest

seed-demo:
	cd generator && uv run fde-gen seed-demo

stats:
	cd generator && uv run fde-gen stats

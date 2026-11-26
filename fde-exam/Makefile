.PHONY: install dev build test ingest bank stats

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

bank:
	cd generator && ./run_bank.sh v2 16 8

stats:
	cd generator && uv run fde-gen stats

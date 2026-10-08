.PHONY: db dev test lint fmt migrate revision

db:  ## Start only Postgres (for local development and tests)
	docker compose up -d db

dev:  ## Run the app with auto-reload against the local database
	uv run alembic upgrade head
	uv run fastapi dev app/main.py

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy

fmt:
	uv run ruff check --fix .
	uv run ruff format .

migrate:
	uv run alembic upgrade head

revision:  ## Usage: make revision m="add users table"
	uv run alembic revision --autogenerate -m "$(m)"

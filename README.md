# Expense Tracker (FastAPI)

A multi-user income and expense tracker with a monthly summary dashboard,
built with FastAPI, PostgreSQL and SQLAlchemy 2.0.

> 🚧 Work in progress. See [docs/DESIGN.md](docs/DESIGN.md) for the design
> decisions and milestones.

## Run it

```bash
docker compose up --build
```

Then open <http://localhost:8000/docs>.

## Develop

Requires [uv](https://docs.astral.sh/uv/) and Docker (for Postgres).

```bash
make db      # start Postgres on localhost:5432
make dev     # apply migrations and run with auto-reload
make seed    # create demo@example.com / demo-password with a year of sample data
make test    # run the test suite (creates the expense_test database if needed)
make lint    # ruff + mypy
```

Copy `.env.example` to `.env` to override settings.

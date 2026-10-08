# Expense Tracker — Design

A multi-user income/expense tracker built with FastAPI and PostgreSQL, with a
monthly summary dashboard. This is a portfolio project: the goal is a clean,
well-tested JSON API (browsable at `/docs`) plus a lightweight server-rendered
web UI on top of it.

This document records the decisions made before writing code and the reasons
behind them.

## Decisions

| # | Topic | Decision | Why |
|---|-------|----------|-----|
| 1 | Users | Multi-user, each with their own account. Every row is owned by a `user_id`. | Shows auth and per-user data isolation. |
| 2 | Architecture | JSON REST API under `/api/...` plus Jinja2 pages served by the same app. Plain JS/HTMX calls the API, and Chart.js draws the charts. | One repo, one deploy, no Node. The API is the main thing to show, and a SPA can be added later. |
| 3 | Auth | JWT access token, accepted from an `httpOnly` + `SameSite=Lax` cookie (web) **or** an `Authorization: Bearer` header (API, `/docs` Authorize button). Passwords hashed with Argon2 via `pwdlib`. Token lifetime is about 1 day. v1 has no refresh tokens and no password reset. | The cookie keeps the token away from JS (XSS), and `SameSite` blocks cross-site POSTs (CSRF). The header supports the standard OAuth2 password flow. |
| 4 | Database | PostgreSQL in every environment (Docker Compose locally, Neon in production, real Postgres in tests). SQLAlchemy 2.0 (typed `Mapped[...]`, **sync**) + Alembic + Pydantic v2. | Monthly grouping uses Postgres-only SQL (`date_trunc`, `generate_series`), so SQLite tests would not prove anything. Sync is simpler, and the app has no I/O concurrency to gain from async. |
| 5 | Data model | Per-user `categories` table, seeded with defaults at registration. Each category is either `income` or `expense`. `amount` is `Numeric(12,2)` and always positive; the sign comes from the category type. THB only. `occurred_on` is a `DATE`. `note` is optional. | Users can start immediately and still customise. `Numeric` avoids float rounding errors. `DATE` avoids timezone drift across month boundaries. |
| 6 | Dashboard | Three stat cards (this month's income / expense / net, each vs last month as %), a 12-month grouped bar chart (income vs expense) with a net line, and a horizontal bar chart of expenses by category for the selected month (click a month to switch). Aggregation happens in SQL, and empty months are filled with 0 via `generate_series`. | Horizontal bars are easier to read than a pie with many slices. Missing months would make the time axis misleading. |
| 7 | Transactions | CRUD; filter by month, type and category; `limit`/`offset` pagination with `total`; filtered sum shown in the header; CSV export. | Covers what a real user needs. Budgets are planned for v2. |
| 8 | Quality | pytest integration tests through `TestClient` against real Postgres, with each test inside a transaction that rolls back. GitHub Actions CI. `uv`, `ruff` (lint + format) and `mypy`. | Tests focus on user isolation, summary correctness and business rules. |
| 9 | Deploy | App on Render (Docker), Postgres on Neon. Everything is configured through env vars (`DATABASE_URL`, `SECRET_KEY`). A **"Try the demo"** button creates a fresh temporary account with 12 months of realistic sample data. Demo accounts older than 24 h are purged on startup and whenever a new demo is created. | Reviewers can try the app in one click without seeing each other's edits, and no external cron is needed. |
| 10 | UI | English UI and README. Amounts shown as `฿1,234.00`. Pico.css with no build step, mobile-friendly. | Aimed at a job-market audience while still respecting the no-Node decision. |

### Explicitly out of scope for v1

- Refresh tokens, password reset, email verification, OAuth login
- Multiple currencies
- Recurring transactions
- Budgets per category (planned for v2)
- Free-text search on notes, CSV import
- Receipt attachments, tags
- Playwright / E2E tests

## Data model

```
users
  id              bigint PK
  email           varchar(254) unique, stored lower-cased
  password_hash   varchar
  is_demo         bool default false
  created_at      timestamptz default now()

categories
  id              bigint PK
  user_id         FK users ON DELETE CASCADE
  name            varchar(50)
  type            varchar(10) CHECK IN ('income','expense')
  created_at      timestamptz
  UNIQUE (user_id, type, lower(name))
  UNIQUE (id, user_id)            -- target of the composite FK below

transactions
  id              bigint PK
  user_id         FK users ON DELETE CASCADE
  category_id     ┐ composite FK (category_id, user_id)
                  ┘   → categories (id, user_id)
  amount          numeric(12,2) CHECK (amount > 0)
  occurred_on     date
  note            varchar(200) null
  created_at      timestamptz
  updated_at      timestamptz
  INDEX (user_id, occurred_on)
```

A transaction's type is always its category's type. To keep that consistent:

- Deleting a category that still has transactions returns **409**. The user
  has to move those transactions to another category first.
- Changing a category's `type` while it has transactions also returns **409**.
- A transaction may only reference a category owned by the same user. The
  composite foreign key enforces this in the database itself, not just in the
  API. It uses `NO ACTION` rather than `RESTRICT` so that deleting a user
  (for example, purging a demo account) can cascade through both tables in
  one statement.

## API sketch

Every resource endpoint is scoped to the current user. If a user asks for
another user's row, the API returns **404**, not 403, so it never reveals that
the row exists.

```
POST   /api/auth/register            create account (+ default categories)
POST   /api/auth/token               OAuth2 password form → bearer token, also sets cookie
POST   /api/auth/logout              clear cookie
POST   /api/auth/demo                create temporary demo account, set cookie
GET    /api/users/me

GET    /api/categories               ?type=
POST   /api/categories
GET    /api/categories/{id}
PATCH  /api/categories/{id}             409 if retyping while in use
DELETE /api/categories/{id}          409 if in use

GET    /api/transactions             ?month=YYYY-MM&type=&category_id=&limit=&offset=
                                     → {items, total, income, expense}
                                       (totals cover every page, not just this one)
POST   /api/transactions             {category_id, amount, occurred_on, note?}
GET    /api/transactions/{id}        → {..., category: {id, name, type}}
PATCH  /api/transactions/{id}        note: null clears the note
DELETE /api/transactions/{id}
GET    /api/transactions/export.csv  same filters, no pagination
```

Amounts are JSON **strings** (`"1234.50"`) so that no client parses them as
floats. Requests accept either strings or numbers.

The list returns `income` and `expense` separately instead of a single `sum`.
Adding the two together without a type filter would mean nothing.

The CSV export starts with a UTF-8 BOM so that Excel shows Thai text
correctly. Any cell beginning with `=`, `+`, `-` or `@` gets an apostrophe in
front to block CSV formula injection. The export is built in memory rather
than streamed: personal data is small, and building it in memory avoids
reading from a DB session after the request's dependencies have closed.

```
GET    /api/summary/monthly          ?from=YYYY-MM&to=YYYY-MM  (inclusive, max 120 months)
                                     → [{month, income, expense, net}], zero-filled
GET    /api/summary/by-category      ?month=YYYY-MM&type=expense
                                     → [{category_id, name, total}] largest first,
                                       categories with no transactions omitted
```

If the months are left out, the summary endpoints default to the current
month in UTC (the last 12 months for `monthly`). The web UI always sends
explicit months computed in the browser's local time, so a user in Bangkok
at 00:30 on the 1st already sees the new month.

Web pages (Jinja2): `/login`, `/register`, `/` (dashboard), `/transactions`,
`/categories`.

## Testing priorities

1. **Isolation:** user A cannot list, read, update or delete user B's
   categories or transactions (404), and cannot attach B's category to their
   own transaction.
2. **Summary correctness:** empty months return 0, the last day of a month
   stays in that month, and decimal totals are exact.
3. **Business rules:** 409 when deleting or retyping a category that is in
   use, and 422 when the amount is ≤ 0.

## Milestones

1. **Skeleton:** uv project, app factory, settings, DB session, Alembic,
   Docker Compose, Dockerfile, ruff/mypy, pytest with a transactional Postgres
   fixture, CI, and a `/healthz` endpoint that checks the database.
2. **Users & auth:** user model, register, token/cookie login, logout, `me`.
3. **Categories:** CRUD with default seeding and the in-use rules. The
   transactions table is created here too, since those rules depend on it.
4. **Transactions:** API for CRUD, filters, pagination, sum, and CSV export.
5. **Summary:** monthly and by-category endpoints.
6. **Web UI:** Jinja2 + Pico.css pages and the Chart.js dashboard.
7. **Demo:** sample data generator, demo endpoint, purge, `make seed`.
8. **Deploy:** Render + Neon, and a README with screenshots and a live link.

# AskIt — Backend API

Real-time quiz platform backend. Hosts run quiz sessions; players join via room code and compete live. Built with FastAPI, PostgreSQL, Redis, and WebSockets.

## Stack

- **Python 3.12** · FastAPI · SQLAlchemy (async) · Alembic
- **PostgreSQL 16** (asyncpg driver)
- **Redis 7** — ephemeral game session state (question order, per-question timers, answer/dedup tracking)
- **Pydantic v2** · PyJWT · Argon2 · structlog · slowapi

## Local setup

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
# 1. Install dependencies
uv sync

# 2. Copy env and fill in values
cp .env.example .env

# 3. Start Postgres + Redis
docker compose up -d askit_db redis

# 4. Apply migrations
uv run alembic upgrade head

# 5. Run the dev server
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Run tests

```bash
uv run pytest
```

Tests use a separate `askit_test` database created automatically by `docker compose up` (see `scripts/create_test_db.sh`). Make sure the containers are running first.

## Architecture

```
app/
├── auth/     # JWT cookie auth, rate limiting
├── game/     # WebSocket game engine, scoring, leaderboard
├── quiz/     # Quiz CRUD, publish/unpublish, favorites, stats
├── user/     # Profile, password change, game history
├── core/     # Exception handlers, middleware, rate limiter
├── models/   # SQLAlchemy ORM models
└── main.py   # App factory, lifespan, routers
```

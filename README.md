# AskIt — Backend API

Real-time quiz platform backend. Hosts run quiz sessions; players join via room code and compete live. Built with FastAPI, PostgreSQL, Redis, and WebSockets.

## Stack

- **Python 3.12** · FastAPI · SQLAlchemy (async) · Alembic
- **PostgreSQL 16** (asyncpg driver)
- **Redis 7** — pub/sub for WebSocket scaling, leaderboard state
- **Pydantic v2** · PyJWT · Argon2 · structlog · slowapi

## Local setup

```bash
# 1. Copy env and fill in values
cp .env.example .env

# 2. Start Postgres + Redis (requires Docker)
docker-compose up -d askit_db redis

# 3. Apply migrations
uv run alembic upgrade head

# 4. Run the dev server
uv run uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

## Run tests

```bash
uv run pytest
```

Tests use a separate `askit_test` database created automatically by `docker-compose up` (see `scripts/create_test_db.sh`). Make sure containers are running before running tests.

## Architecture

```
app/
├── auth/        # JWT cookie auth, rate limiting
├── game/        # WebSocket game engine, scoring, leaderboard
├── quiz/        # Quiz CRUD, publish/unpublish, favorites, stats
├── user/        # Profile, password change, game history
├── core/        # Exception handlers, limiter
├── models/      # SQLAlchemy ORM models
└── main.py      # App factory, middleware, routers
```

Detailed module docs in `docs/`:
- `AUTH_MODULE.md` — token lifecycle, cookie strategy
- `GAME_MODULE.md` — WebSocket protocol, Redis keys, game state machine
- `USER_MODULE.md` — profile and history endpoints
- `DATABASE_SCHEMA.md` — full ERD and table descriptions
- `API_DESIGN_RULES.md` — naming conventions, error envelope format

## WebSocket game protocol

Connect: `ws://localhost:8000/ws/game/{room_code}?playerId={id}`

Key server→client events: `room_state`, `player_joined`, `game_starting`, `question`, `answer_result`, `question_ended` (with `answerDistribution`), `leaderboard` (with `change`), `game_finished`.

Key client→server events: `start_game`, `submit_answer`.

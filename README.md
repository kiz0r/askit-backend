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

Tests use a separate `askit_test` database created automatically by `docker compose up` (see `scripts/create_test_db.sh`). Make sure the containers are running first. Copy `.env` to `.env.test` and point the hosts at `localhost`, since the suite runs outside the containers.

## Deployment

`docker-compose.yml` is the deployable stack and publishes nothing but the API,
on the loopback interface, for a reverse proxy to pick up. Postgres and Redis
are reachable only over the compose network.

`docker-compose.override.yml` holds the development conveniences: it publishes
the database and Redis ports so the test suite can reach them from the host, and
mounts the working copy for live reload. Compose loads it automatically, so
`docker compose up` is the development command and deployment passes the base
file explicitly:

```bash
docker compose -f docker-compose.yml up -d --build
```

The split is this way round because an override cannot withdraw a published
port; overrides append to the ports list. Making the base the closed one means a
forgotten flag yields a closed stack rather than an exposed database.

The API applies `alembic upgrade head` before it starts serving, and waits for
the database and Redis health checks first, so a fresh host needs no manual
migration step.

For `.env` on a deployed host:

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `production` — this is what marks the auth cookies `Secure` |
| `LOG_JSON` | `true` |
| `CORS_ORIGINS` | the site origin, no trailing slash |
| `POSTGRES_HOST` | `askit_db` — the service name, not `localhost` |
| `REDIS_HOST` | `redis` |
| `REDIS_PASSWORD`, `POSTGRES_PASSWORD` | fresh values |
| `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET` | fresh values, never the development ones |

TLS is not optional: in production the auth cookies carry `Secure`, so over
plain HTTP the browser discards them and nobody can sign in. Terminating TLS at
the proxy and serving the frontend from the same origin also keeps `SameSite=Lax`
effective and takes CORS out of the picture entirely.

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

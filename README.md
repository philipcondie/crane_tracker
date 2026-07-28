# Crane Spotter

Web app for tracking cranes at construction sites.

A FastAPI backend with a PostGIS-backed PostgreSQL database, deployed to a DigitalOcean droplet behind a Caddy reverse proxy with automatic HTTPS.

## Tech stack

- **API:** FastAPI + Uvicorn, with SlowAPI rate limiting
- **Database:** PostgreSQL (PostGIS) via SQLAlchemy, migrations with Alembic
- **Packaging:** [uv](https://docs.astral.sh/uv/)
- **Deploy:** Docker Compose + Caddy on a DO droplet, CI/CD via GitHub Actions

## Submission safeguards

- Crane creation is limited per resolved client IP. The limit is configured with
  `CREATE_RATE_LIMIT` and defaults to `5/hr`.
- A crane within 100 metres of an existing crane is treated as a possible duplicate.
  Clients may explicitly override that warning when the crane is genuinely distinct.
- Gone reports are deduplicated using an HMAC hash of the resolved client IP; raw
  reporter addresses are not stored.

SlowAPI uses in-memory counters in the current single-process deployment. Counters
reset when the app restarts, and shared storage will be required before running
multiple app workers or replicas.

## Local development

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```bash
uv sync                                   # install dependencies
docker compose up -d db test_db           # start local + test Postgres (host ports 5531 / 5532)
ENVIRONMENT=development uv run alembic upgrade head   # apply migrations
uv run uvicorn app.main:app --reload      # run the API at http://localhost:8000
```

Run the checks:

```bash
uv run pytest             # tests
uv run ruff check .       # lint
uv run ruff format .      # format
```

Copy `.env.example` to `.env` and provide the database URLs, CORS origins, and
`IP_HASH_SALT`. Set `CREATE_RATE_LIMIT=5/hr` or omit the variable to use that default;
do not leave it empty. Values use SlowAPI/limits syntax such as `10/minute`.

## Project layout

Runtime code lives in `app/` — `routes/` (HTTP handlers), `services/` (business/DB logic),
`models/` (SQLAlchemy), `schemas/` (Pydantic), `core/` (config, database, dependencies).
Migrations are in `alembic/versions/`. Tests mirror the app layers under `tests/`.

## Deployment

Production runs via `docker-compose.prod.yml` (db, one-shot migrate, app, Caddy). Pushing to
`main` triggers `.github/workflows/deploy.yml`, which SSHes to the droplet, rebuilds, runs
migrations, restarts the app, and health-checks — rolling back on failure. See `AGENTS.md`
for the full deployment reference.

Caddy is assigned `172.28.0.2` on the production Compose network. Uvicorn is started
with proxy-header handling enabled and trusts forwarded headers only from that address,
so `request.client.host` contains the public client address used by rate limiting and
gone-report deduplication. The FastAPI application does not process
`X-Forwarded-For` directly.

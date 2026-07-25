# Crane Spotter

Web app for tracking cranes at construction sites.

A FastAPI backend with a PostGIS-backed PostgreSQL database, deployed to a DigitalOcean droplet behind a Caddy reverse proxy with automatic HTTPS.

## Tech stack

- **API:** FastAPI + Uvicorn
- **Database:** PostgreSQL (PostGIS) via SQLAlchemy, migrations with Alembic
- **Packaging:** [uv](https://docs.astral.sh/uv/)
- **Deploy:** Docker Compose + Caddy on a DO droplet, CI/CD via GitHub Actions

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

## Project layout

Runtime code lives in `app/` — `routes/` (HTTP handlers), `services/` (business/DB logic),
`models/` (SQLAlchemy), `schemas/` (Pydantic), `core/` (config, database, dependencies).
Migrations are in `alembic/versions/`. Tests mirror the app layers under `tests/`.

## Deployment

Production runs via `docker-compose.prod.yml` (db, one-shot migrate, app, Caddy). Pushing to
`main` triggers `.github/workflows/deploy.yml`, which SSHes to the droplet, rebuilds, runs
migrations, restarts the app, and health-checks — rolling back on failure. See `AGENTS.md`
for the full deployment reference.

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

Photo uploads use Cloudflare R2 through its S3-compatible API. Configure
`R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, and
`R2_PUBLIC_BASE_URL`. The endpoint URL has the form
`https://<account-id>.r2.cloudflarestorage.com`; the public base URL should be the
bucket's `r2.dev` URL or custom public domain.

Uploads accept JPEG, PNG, WebP, HEIC, and HEIF files up to 10 MB. Images are decoded
and re-encoded before storage to remove EXIF/GPS metadata; HEIC and HEIF inputs are
stored as browser-compatible JPEGs. GIF uploads are not supported.

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


## Workers

The worker processes queued photo deletions from R2 and cleans up expired pending
uploads. Run one worker alongside the API; multiple workers have not been tested
for race conditions.

After completing the local setup above, start the worker from the repository root
in a separate terminal:

```bash
ENVIRONMENT=development uv run python -m app.worker.main
```

The worker reads `.env` and uses the same `DATABASE_URL` and R2 configuration as
the API. Ensure the database is running and migrations have been applied. Set
`ENVIRONMENT=development` in `.env` to omit the command's environment prefix.
For the numeric worker settings in `.env.example`, supply values or remove the
entries to use defaults; empty values are invalid. Defaults include
`JOB_BATCH_SIZE=5`, `WORKER_SLEEP_PERIOD=5` (seconds), and `MAX_WORKER_ATTEMPTS=5`.
Press Ctrl+C to stop the worker gracefully.

Start the worker in the background using the production Compose environment
(`.env.prod`):

```bash
docker compose -f docker-compose.prod.yml up -d --build worker
```

Compose waits for migrations to complete before starting the worker and restarts
it unless explicitly stopped. View its logs or stop it with:

```bash
docker compose -f docker-compose.prod.yml logs -f worker
docker compose -f docker-compose.prod.yml stop worker
```

## Admin photo review

Apply migrations before starting the API, then provision an admin locally:

```bash
ENVIRONMENT=development uv run alembic upgrade head
uv run python -m app.admin reviewer
```

The command prompts for a password (at least 15 characters) without putting it in
shell history. In production, run the same command inside the app container with
`docker compose -f docker-compose.prod.yml exec app python -m app.admin reviewer`.
There is no public account registration endpoint.

Send `POST /admin/login` with JSON `{"username":"reviewer","password":"..."}`.
The response contains `access_token`, `token_type` and `expires_in`. Supply
`Authorization: Bearer <access_token>` to review completed uploads with
`GET /cranes/photos?limit=50` (1–100) and delete a photo with
`DELETE /cranes/{crane_id}/photos/{photo_id}`. The review response has `photos` and
`end`; use the last photo's `id` as `cursor` to fetch the next page. Deletion queues
the existing background storage cleanup. Reviewing here means browsing uploaded
photos and deleting unwanted ones; there is no approval state.

`POST /admin/logout` with the same bearer header revokes that token. Tokens expire
in one hour by default (`ADMIN_TOKEN_TTL_SECONDS`, 60–86400). Sign-in is limited per
resolved client IP (`ADMIN_LOGIN_RATE_LIMIT`, default `5/minute`). Admin passwords
use salted scrypt; only SHA-256 hashes of random session tokens are stored. Setting
an account's `is_active` to false immediately blocks its existing sessions.

Use HTTPS in production and keep bearer tokens in memory in an admin client.
Public crane reads, creation, gone reports and photo uploads require no sign-in.
This repository provides the API workflow; an admin browser interface is not yet
included.

Password hashing and hashed session storage follow the
[OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
and [session guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Reporting photos

Anyone can send `POST /cranes/{crane_id}/photos/{photo_id}/report` without a
request body or sign-in. A successful report returns 201. Repeat reports from the
same client IP for the same photo return 409; nonexistent, unfinished or deleted
photos (including a mismatched crane ID) return 404. Reports store an HMAC hash of
the resolved client IP using `IP_HASH_SALT`, never the raw address. Reporting is
limited per client IP by `PHOTO_REPORT_RATE_LIMIT` (default `10/hour`); exceeding
it returns 429. Shared IPs count as one reporter per photo.

The authenticated `GET /cranes/photos` response includes `reportCount` on each
photo. Add `reported_only=true` to review only photos with reports; existing cursor
pagination and newest-first ordering apply. Public photo responses omit report
information. Reports do not hide or delete photos automatically; admins use the
existing authenticated delete endpoint after review. Reports are removed when
the worker permanently deletes the photo record.

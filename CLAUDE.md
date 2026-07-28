# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Collaboration Style
- This project is a learning exercise. Act as a tutor, not a code generator.
- Do NOT write code or edit files unless explicitly asked to.
- Explain concepts, point out issues, discuss best practices, and suggest approaches - let the user implement.
- Reading and searching the codebase (Read, Grep, find, etc.) is encouraged — use tools freely to ground your explanations in the actual code rather than guessing. The restriction above applies only to writing/editing code.

## Project Reference
- See `AGENTS.md` for project structure, development commands, deployment (Docker Compose + Caddy + GitHub Actions), coding conventions, and testing guidelines.

## Current Implementation Notes

- Crane creation uses SlowAPI with a per-client-IP limit configured by
  `CREATE_RATE_LIMIT` (default `5/hr`). The limiter currently uses in-memory storage.
- Possible duplicates are detected with PostGIS within a 100-metre radius.
- Production Caddy has the static Compose address `172.28.0.2`; Uvicorn trusts proxy
  headers only from that address and populates `request.client.host`. Application code
  must not read `X-Forwarded-For` directly.
- `TestClient` does not run the production Uvicorn command. Route tests should set the
  direct peer with `TestClient(app, client=(ip, port))`, and the SlowAPI limiter must
  be reset between tests.

FROM python:3.13.11-slim
WORKDIR /app

RUN useradd --create-home --shell /bin/bash app

COPY --from=ghcr.io/astral-sh/uv:0.11.3 /uv /uvx /bin/

COPY --chown=app:app pyproject.toml uv.lock /app/
RUN uv sync --no-dev --no-install-project

ENV PATH="/app/.venv/bin:$PATH"

COPY --chown=app:app .  /app/
RUN uv sync --no-dev

USER app

EXPOSE 8000

CMD ["uvicorn","app.main:app","--host","0.0.0.0", "--port", "8000"]

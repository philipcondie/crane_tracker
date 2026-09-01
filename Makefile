.PHONY: help lint format clean test test-integration

lint:
	uv run ruff format .
	uv run ruff check . --fix

clean:
	uv run ruff check . --fix

format:
	uv run ruff format .

test:
	uv run pytest

test-integration:
	uv run pytest --integration -m integration

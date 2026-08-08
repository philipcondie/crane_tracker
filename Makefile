.PHONY: help lint format clean test

lint:
	uv run ruff format .
	uv run ruff check . --fix

clean:
	uv run ruff check . --fix

format:
	uv run ruff format .

test:
	uv run pytest

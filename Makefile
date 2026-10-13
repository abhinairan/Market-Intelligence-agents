# Thin wrapper over the halyard CLI. All sequencing lives in Python (src/halyard/cli.py),
# so `make` is optional: every target below is one `halyard ...` command.

.PHONY: install up down wipe build demo eval test lint

install:
	uv sync

up: install
	uv run halyard up

down:
	uv run halyard down

wipe:
	uv run halyard down --wipe

build: install
	uv run halyard build

demo: install
	uv run halyard demo

eval: install
	uv run halyard eval

test: install
	uv run pytest

lint:
	uv run ruff check src tests

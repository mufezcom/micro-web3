UV ?= uv

.PHONY: all sync lint format test live-test build clean

all: lint

sync:
	$(UV) sync --all-groups

lint:
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	$(UV) run pyrefly check

format:
	$(UV) run ruff check --fix .
	$(UV) run ruff format .

test:
	$(UV) run pytest

live-test:
	@test -n "$(MICRON_RPC_URL)" || { echo "MICRON_RPC_URL is not set"; exit 1; }
	$(UV) run pytest tests/test_live.py

build:
	$(UV) build

clean:
	rm -rf dist .pytest_cache .ruff_cache

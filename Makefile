.PHONY: init install run test lint build publish clean

DIST_DIR := dist

init:
	@command -v uv >/dev/null 2>&1 || { echo >&2 "Error: uv is not installed."; exit 1; }

install: init
	@uv sync

run: init
	@uv run multimodal-reader-mcp

test: init
	@uv run -m pytest

lint: init
	@uv run ruff check .

build: init
	@rm -rf $(DIST_DIR)
	@uv build
	@ls -la $(DIST_DIR)

publish: build
	@test -n "$$UV_PUBLISH_TOKEN" || { echo >&2 "Error: UV_PUBLISH_TOKEN is not set"; exit 1; }
	@uv publish

clean:
	@rm -rf $(DIST_DIR) .pytest_cache .ruff_cache .mypy_cache __pycache__ multimodal_reader_mcp/__pycache__

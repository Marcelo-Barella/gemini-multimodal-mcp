# AGENTS.md

## Cursor Cloud specific instructions

### Overview

Single-service Python MCP server (`multimodal-reader-mcp`) that reads local audio/video files via Google Gemini and returns structured analysis over stdio. No database, no Docker, no frontend.

### Prerequisites

- `uv` (installed to `~/.local/bin` by the update script)
- Python 3.14 (installed by `uv python install 3.14` in the update script)
- `GOOGLE_API_KEY` environment variable required at runtime (not for tests -- tests fully mock the Gemini API)

### Common commands

All standard dev commands are in the `Makefile`:

| Task | Command |
|------|---------|
| Install deps | `make install` (or `uv sync`) |
| Lint | `make lint` (or `uv run ruff check .`) |
| Test | `make test` (or `uv run -m pytest`) |
| Build | `make build` (or `uv build`) |
| Run server | `make run` (or `uv run multimodal-reader-mcp`) |

### Gotchas

- The server runs over **stdio** (not HTTP). To test it, pipe JSON-RPC messages into it: `echo '{"jsonrpc":"2.0","id":1,"method":"initialize",...}' | GOOGLE_API_KEY=dummy uv run multimodal-reader-mcp`.
- Tests pass without `GOOGLE_API_KEY` because all Gemini calls are mocked.
- `MULTIMODAL_READER_MODEL` env var optionally overrides the default Gemini model (`gemini-2.5-flash`).

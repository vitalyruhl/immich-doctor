# Development Commands

- Python lint: `uv run ruff check .`
- Python format check: `uv run ruff format --check .`
- Python tests: `uv run pytest`
- Frontend install from lockfile: `npm ci` in `ui/frontend`
- Frontend tests: `npm test` in `ui/frontend`
- Frontend build/typecheck: `npm run build` in `ui/frontend`
- Frontend audit gate used during dependency work: `npm audit --audit-level=moderate` in `ui/frontend`
- Before reporting CI parity for lint, run both Ruff check and Ruff format check; CI runs both.
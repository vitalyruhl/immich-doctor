# Development

## Local setup

```bash
uv sync --dev
```

If you want to enter the managed environment directly:

```powershell
uv run python -m immich_doctor --help
```

## Useful commands

```bash
uv run python -m immich_doctor --help
uv run python -m immich_doctor runtime health check
uv run python -m immich_doctor runtime validate
uv run python -m immich_doctor storage paths check --output json
uv run python -m immich_doctor storage permissions check
uv run python -m immich_doctor backup verify
uv run python -m immich_doctor db health check
uv run python -m immich_doctor db performance indexes check
pytest
ruff check .
ruff format --check .
docker compose -f docker/docker-compose.yml up --build
```

## Development expectations

- keep changes small
- keep service boundaries clean
- add tests with behavior changes
- update docs when scope or configuration changes

Container-oriented work should additionally validate:

- `docker build -f docker/Dockerfile .`
- `docker compose -f docker/docker-compose.yml up --build`

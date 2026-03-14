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
uv run python -m immich_doctor health ping
uv run python -m immich_doctor config validate --output json
uv run python -m immich_doctor backup validate
uv run python -m immich_doctor runtime validate
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

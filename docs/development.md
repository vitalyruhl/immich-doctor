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
uv run python -m immich_doctor analyze catalog scan-job status
uv run python -m immich_doctor analyze catalog scan-job start --force
uv run python -m immich_doctor analyze catalog scan-job pause
uv run python -m immich_doctor analyze catalog scan-job resume
uv run python -m immich_doctor analyze catalog scan-job stop
uv run python -m immich_doctor analyze catalog scan-job workers --workers 8
uv run python -m immich_doctor storage paths check --output json
uv run python -m immich_doctor storage permissions check
uv run python -m immich_doctor backup files
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
- keep docs explicit about what is already implemented vs. still planned

Container-oriented work should additionally validate:

- `docker build -f docker/Dockerfile .`
- `docker compose -f docker/docker-compose.yml up --build`

Note:

- `backup files` is legacy
- the primary backup workflow under active development is the target-based manual execution path in the backup UI/API

# Docker Runtime Guide

## Purpose

The Docker setup is intentionally safe by default.
The runtime image now starts a single HTTP server that serves both the FastAPI
backend and the built Vue frontend from the same container.

## Files

- `docker/Dockerfile`
- `docker/docker-compose.yml`
- `docker/docker-compose.dev.yml`
- `docker/docker-compose.unraid.yml`

## Build the image

```bash
docker build -f docker/Dockerfile -t immich-doctor:local .
```

## Local runtime validation

```bash
docker compose -f docker/docker-compose.yml up --build
```

This publishes:

```text
http://localhost:8000/
```

API example:

```text
http://localhost:8000/api/health/overview
```

To run a one-off command:

```bash
docker compose -f docker/docker-compose.yml run --rm immich-doctor python -m immich_doctor runtime validate
```

To use the long-running container and then execute checks manually:

```bash
docker exec -it immich-doctor python -m immich_doctor runtime validate
docker exec -it immich-doctor python -m immich_doctor storage paths check
docker exec -it immich-doctor python -m immich_doctor storage permissions check
docker exec -it immich-doctor python -m immich_doctor backup files
docker exec -it immich-doctor python -m immich_doctor backup verify
docker exec -it immich-doctor python -m immich_doctor db health check
docker exec -it immich-doctor python -m immich_doctor db performance indexes check
```

## Local development container

```bash
docker compose -f docker/docker-compose.dev.yml run --rm immich-doctor
```

Useful development commands:

```bash
docker compose -f docker/docker-compose.dev.yml run --rm immich-doctor uv run pytest
docker compose -f docker/docker-compose.dev.yml run --rm immich-doctor uv run python -m immich_doctor --help
```

## Unraid-style deployment

```bash
docker compose --env-file .env -f docker/docker-compose.unraid.yml up -d
```

For Unraid, set the Web UI field to:

```text
http://[IP]:[PORT]/
```

Recommended Unraid mount pattern:

- Immich source storage: read-only
- backup destination: writable
- reports, manifests, quarantine, logs, tmp: writable
- config directory: writable

Example host path styles:

- `/mnt/user/...`
- `/mnt/diskX/...`
- `/mnt/user/images/immich`
- `/mnt/user/appdata/immich-doctor/...`
- `/mnt/user/backups/immich-doctor`

See `docs/unraid.md` for the Unraid-specific setup flow and `.env.unraid.example` for recommended environment values.

## Runtime and HTTP behavior

The container HTTP entrypoint is:

```bash
uvicorn immich_doctor.api:app --host 0.0.0.0 --port 8000
```

The backend serves:

- the Vue app on `/`
- hashed frontend assets on `/assets`
- SPA fallback for deep links such as `/dashboard`
- API endpoints under `/api`

`runtime validate` still checks:

- package startup
- effective UID, GID, username, group, working directory, and umask

Additional canonical commands:

- `backup files`
- `storage paths check`
- `storage permissions check`
- `backup verify`
- `db health check`
- `db performance indexes check`

Current backup status in Docker:

- implemented: `backup files` for one local, versioned rsync-based file backup plus persisted snapshot metadata
- implemented: `backup verify` for backup target readiness checks plus snapshot manifest structure checks
- not implemented yet: DB backup, metadata backup, remote targets, retention, restore, backup-all orchestration

## Non-root vs root

Default recommendation:

- run as non-root
- set `PUID`, `PGID`, and `UMASK` explicitly for Unraid

Fallback:

- use root only if a host filesystem or mount setup makes non-root technically impossible

## Safety notes

- never mount source storage writable unless you have a very specific reason
- keep reports and quarantine on writable persistent storage
- use runtime, storage, backup, and db validation before any future backup or repair workflow
- the current container flow does not perform destructive actions
- the container keeps all CLI commands available via `docker exec`

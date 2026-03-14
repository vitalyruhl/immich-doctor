# Docker Runtime Guide

## Purpose

The Docker setup is intentionally safe by default.
The default container command only runs runtime validation and does not modify user data.

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

To run a one-off command:

```bash
docker compose -f docker/docker-compose.yml run --rm immich-doctor python -m immich_doctor runtime validate
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

## Runtime validation behavior

`runtime validate` checks:

- package startup
- effective UID, GID, username, group, working directory, and umask

Additional canonical commands:

- `storage paths check`
- `storage permissions check`
- `backup verify`
- `db health check`
- `db performance indexes check`

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

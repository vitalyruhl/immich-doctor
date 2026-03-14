# Configuration

`immich-doctor` currently uses environment variables, optionally loaded from a
local `.env` file.

The application accepts both:

- the original `IMMICH_DOCTOR_*` variables
- shorter Docker-friendly aliases such as `IMMICH_STORAGE_PATH`, `REPORTS_PATH`, and `DB_HOST`

## Core variables

| Variable | Purpose | Required now |
| --- | --- | --- |
| `IMMICH_DOCTOR_ENVIRONMENT` | Runtime environment label | No |
| `IMMICH_DOCTOR_IMMICH_LIBRARY_ROOT` or `IMMICH_STORAGE_PATH` | Main Immich storage root | Recommended |
| `IMMICH_DOCTOR_IMMICH_UPLOADS_PATH` or `IMMICH_UPLOADS_PATH` | Upload directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_THUMBS_PATH` or `IMMICH_THUMBS_PATH` | Thumbnail directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_PROFILE_PATH` or `IMMICH_PROFILE_PATH` | Profile image directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_VIDEO_PATH` or `IMMICH_VIDEO_PATH` | Encoded video directory path | Recommended |
| `IMMICH_DOCTOR_BACKUP_TARGET_PATH` or `BACKUP_TARGET_PATH` | Backup target directory | Recommended |
| `IMMICH_DOCTOR_CONFIG_PATH` or `CONFIG_PATH` | Optional config directory | No |
| `IMMICH_DOCTOR_POSTGRES_DSN` | PostgreSQL connection string | Optional |
| `DB_HOST` | PostgreSQL hostname for runtime validation | Optional |
| `DB_PORT` | PostgreSQL port | Optional |
| `DB_NAME` | PostgreSQL database name | Optional |
| `DB_USER` | PostgreSQL username | Optional |
| `DB_PASSWORD` | PostgreSQL password | Optional |
| `IMMICH_DOCTOR_POSTGRES_CONNECT_TIMEOUT_SECONDS` or `DB_CONNECT_TIMEOUT_SECONDS` | PostgreSQL connect timeout | No |

## Runtime artifact paths

| Variable | Default |
| --- | --- |
| `IMMICH_DOCTOR_REPORTS_PATH` or `REPORTS_PATH` | `data/reports` |
| `IMMICH_DOCTOR_MANIFESTS_PATH` or `MANIFESTS_PATH` | `data/manifests` |
| `IMMICH_DOCTOR_QUARANTINE_PATH` or `QUARANTINE_PATH` | `data/quarantine` |
| `IMMICH_DOCTOR_LOGS_PATH` or `LOG_PATH` | `data/logs` |
| `IMMICH_DOCTOR_TMP_PATH` or `TMP_PATH` | `data/tmp` |

## Docker and Unraid identity variables

The compose files support:

| Variable | Purpose |
| --- | --- |
| `PUID` | Effective runtime user ID |
| `PGID` | Effective runtime group ID |
| `UMASK` | File creation mask applied by the entrypoint |

The default recommendation is non-root execution.
If a specific host mount really requires it, root can still be used explicitly by
setting `PUID=0` and `PGID=0`.

## External tools

The MVP can validate that required tools are available on `PATH`.

| Variable | Format |
| --- | --- |
| `IMMICH_DOCTOR_REQUIRED_EXTERNAL_TOOLS` | comma-separated list |
| `IMMICH_DOCTOR_OPTIONAL_EXTERNAL_TOOLS` | comma-separated list |

## PostgreSQL configuration examples

```text
postgresql://immich:immich@postgres:5432/immich
```

```text
DB_HOST=postgres
DB_PORT=5432
DB_NAME=immich
DB_USER=immich
DB_PASSWORD=change-me
```

## Validation behavior

Current command behavior:

- `health ping` does not require infrastructure configuration
- `config validate` validates configured Immich paths and PostgreSQL connectivity if a DSN is present
- `backup validate` validates backup target writability and configured required tools
- `runtime validate` validates runtime identity, configured mounts, read/write access, and database reachability

## Notes for Docker and Unraid usage

- mount Immich storage read-only whenever possible
- mount backup destinations explicitly
- mount report, manifest, quarantine, log, and temp directories separately
- mount the optional config directory read-only
- provide PostgreSQL connectivity through `DB_*` values or `IMMICH_DOCTOR_POSTGRES_DSN`

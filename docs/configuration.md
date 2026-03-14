# Configuration

`immich-doctor` currently uses environment variables, optionally loaded from a
local `.env` file.

## Core variables

| Variable | Purpose | Required now |
| --- | --- | --- |
| `IMMICH_DOCTOR_ENVIRONMENT` | Runtime environment label | No |
| `IMMICH_DOCTOR_IMMICH_LIBRARY_ROOT` | Main Immich storage root | Recommended |
| `IMMICH_DOCTOR_IMMICH_UPLOADS_PATH` | Upload directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_THUMBS_PATH` | Thumbnail directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_PROFILE_PATH` | Profile image directory path | Recommended |
| `IMMICH_DOCTOR_IMMICH_VIDEO_PATH` | Encoded video directory path | Recommended |
| `IMMICH_DOCTOR_BACKUP_TARGET_PATH` | Backup target directory | Yes for `backup validate` |
| `IMMICH_DOCTOR_POSTGRES_DSN` | PostgreSQL connection string | Optional in MVP |
| `IMMICH_DOCTOR_POSTGRES_CONNECT_TIMEOUT_SECONDS` | PostgreSQL connect timeout | No |

## Runtime artifact paths

| Variable | Default |
| --- | --- |
| `IMMICH_DOCTOR_REPORTS_PATH` | `data/reports` |
| `IMMICH_DOCTOR_MANIFESTS_PATH` | `data/manifests` |
| `IMMICH_DOCTOR_QUARANTINE_PATH` | `data/quarantine` |
| `IMMICH_DOCTOR_LOGS_PATH` | `data/logs` |
| `IMMICH_DOCTOR_TMP_PATH` | `data/tmp` |

## External tools

The MVP can validate that required tools are available on `PATH`.

| Variable | Format |
| --- | --- |
| `IMMICH_DOCTOR_REQUIRED_EXTERNAL_TOOLS` | comma-separated list |
| `IMMICH_DOCTOR_OPTIONAL_EXTERNAL_TOOLS` | comma-separated list |

## PostgreSQL DSN example

```text
postgresql://immich:immich@postgres:5432/immich
```

## Validation behavior

Current command behavior:

- `health ping` does not require infrastructure configuration
- `config validate` validates configured Immich paths and PostgreSQL connectivity if a DSN is present
- `backup validate` validates backup target writability and configured required tools

## Notes for Docker and Unraid usage

- mount Immich storage read-only whenever possible
- mount backup destinations explicitly
- mount report, manifest, quarantine, log, and temp directories separately
- provide PostgreSQL connectivity through `IMMICH_DOCTOR_POSTGRES_DSN`


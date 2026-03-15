# Backup workflow

Status: active

## Implemented now

- `backup verify`
  - validates backup target readiness and configured required tools
- `backup files`
  - runs one local, versioned file backup from the configured Immich library root
  - uses the backup application layer, not direct CLI subprocess calls
  - uses non-destructive rsync defaults

## Planned next

- manifest generation and persistence
- DB backup inclusion
- metadata capture
- backup-all orchestration
- retention
- remote targets

## Still out of scope

- restore
- destructive cleanup defaults
- scheduler / cron

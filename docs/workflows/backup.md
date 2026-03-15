# Backup workflow

Status: active

## Implemented now

- `backup verify`
  - validates backup target readiness and configured required tools
- `backup files`
  - runs one local, versioned file backup from the configured Immich library root
  - uses the backup application layer, not direct CLI subprocess calls
  - uses non-destructive rsync defaults
- repair safety foundation now reserves nullable `pre_repair_snapshot_id` and
  `post_repair_snapshot_id` fields on persisted `RepairRun` records for later
  backup/repair integration

## Planned next

- manifest generation and persistence
- DB backup inclusion
- metadata capture
- backup-all orchestration
- retention
- remote targets
- pre-repair and post-repair snapshot integration for mutating repair flows

## Still out of scope

- restore orchestration is still not implemented, but remains a required later safety layer
- destructive cleanup defaults
- scheduler / cron

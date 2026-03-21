# Backup Execution

Status: active

## Primary flow

The primary executable backup flow is the target-based manual backup execution
path behind the backup UI and API.

Current primary orchestrator:

- `ManualBackupExecutionService`

It now owns:

- target validation gate
- prepared target access
- destination semantics
- execution dispatch
- job/result mapping

## Prepared execution semantics

The primary flow prepares a small execution context before dispatch.

That context distinguishes:

- path-like usable destinations
- transport-prepared destinations
- mirror/sync destinations
- versioned snapshot destinations

This keeps the execution model centered on safety and workflow usefulness, not
on transport alone.

## Executable target modes now

- local targets: executable through the asset-aware check/sync mirror workflow
- SMB `pre_mounted_path`: executable when the mounted path is already usable
- SSH and rsync safe subset: executable through conservative files-only,
  versioned snapshot transfer

Still unsupported for execution:

- SMB `system_mount`
- SSH/rsync password auth

## Legacy flow

`backup files` remains available as a legacy local files-only path.

It is no longer the primary backup workflow and should not keep growing as a
parallel execution architecture.

# Backup Targets

Status: active

## Minimal SSH config philosophy

SSH and rsync targets share the same remote connection model:

- `host`
- `username`
- `port`
- `auth_mode`
- `known_host_mode`
- `known_host_reference`

Execution behavior differs later in the execution layer only. Configuration and
validation intentionally use one shared model.

Minimal SSH configuration is meant to match real operators:

- a connection string such as `root@192.168.2.2` is accepted
- the backend parses that shorthand into `username=root` and `host=192.168.2.2`
- `auth_mode=agent` is valid and must not force an explicit private key in the UI
- `known_host_mode=strict` uses the configured known-hosts file or the default
  `~/.ssh/known_hosts`
- `known_host_mode=accept_new` allows first contact while still writing to a
  known-hosts file
- `known_host_mode=disabled` is dangerous, must stay visibly flagged, and maps
  only to `StrictHostKeyChecking=no`

Current remote auth modes:

- `agent`: supported for validation and execution
- `private_key`: supported for validation and execution through the existing
  local secret store
- `password`: modelled for future use, but execution remains disabled

## SMB authentication requirements

SMB keeps two valid transport modes:

1. `pre_mounted_path`

- requires `mounted_path`
- does not require credentials in the target record
- assumes the operating system already mounted and authenticated the share
- executes through the same path-like check/sync workflow as other mounted
  destinations when the mounted path is usable

2. `system_mount`

- requires `username`
- requires `password_secret_ref`
- allows optional `domain`
- allows optional `mount_options`

SMB `system_mount` targets stay configuration and validation only in this phase.
Only `pre_mounted_path` is executable now, and only because it resolves to an
already mounted usable path.

## What to enter in the UI

- Local folder on this system:
  Enter one usable local path. This can also be a path already mounted into the
  host or container.
- SMB mounted local path:
  Enter only the mounted local path. Doctor treats this like another usable
  local path and does not need SMB server/share credentials for execution.
- SMB system mount:
  Enter server/host, share name, optional subfolder inside the share, username,
  and password secret. Share means the SMB share root such as `backups`;
  subfolder means an optional path inside that share such as `immich`.
- SSH target:
  Prefer the SSH connection shorthand such as `backup@example-host` or
  `backup@example-host:2222`. Separate host/user/port fields are secondary.
- Rsync over SSH:
  Uses the same connection model as SSH. This is SSH-based transport, not a
  mounted filesystem or NFS-style path.

Local folder and SMB mounted local path differ mainly by operator intent:

- local folder: regular local or already-mounted storage path on this system
- SMB mounted local path: the path comes from an SMB share that was mounted
  outside doctor already

## Security model

Backup target secrets are write-only from the UI perspective.

Rules:

- raw passwords and private keys are never returned by the API
- masked secrets are not returned
- fingerprints, lengths, and partial secret echoes are not returned
- UI edit forms keep secret inputs empty
- empty secret input means keep the stored secret reference
- filled secret input means replace the stored secret reference
- when auth or mount mode makes a stored secret irrelevant, the backend clears
  that secret reference
- validation and execution load secrets internally from the stored reference

Stored backup target records may contain:

- `password_secret_ref`
- `private_key_secret_ref`

Stored backup target records must never contain:

- `password`
- raw private key material

## Future execution phases

Implemented now:

- local targets: validation, check/sync, representative test copy, selective
  restore with quarantine-first overwrite protection
- SSH and rsync targets: conservative files-only execution for the supported
  auth subset
- SMB `pre_mounted_path` targets: path-like validation, check/sync, and the
  same asset-aware mirror workflow as other usable mounted destinations
- SMB `system_mount` targets: validation and planning only

Not enabled now:

- productive SMB system-mount execution
- password-based SSH or rsync execution
- restore execution for remote targets
- new secret infrastructure beyond the existing local secret store

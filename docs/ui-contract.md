# UI Contract

## Purpose

The operational UI must remain a thin orchestration layer over backend truth.
Routes and navigation may expose planned product areas, but they must not imply
that matching backend capabilities already exist.

## Canonical API prefix

All UI-facing backend endpoints live under:

```text
/api
```

## Runtime integrity contract

The canonical runtime integrity endpoints are:

```text
GET /api/runtime/integrity/inspect
GET /api/runtime/metadata-failures/inspect
POST /api/runtime/metadata-failures/repair
```

Rules:

- physical file integrity must be inspected before metadata failure diagnosis
- metadata failures must not collapse into generic failed counts without
  per-asset root-cause classification
- repair remains dry-run by default
- apply-capable actions must be explicitly identified by the backend contract
- unsupported schema or missing tooling must remain visible, never fake `OK`

## Settings contract

The canonical settings endpoints are:

```text
GET /api/settings
GET /api/settings/schema
PUT /api/settings
```

Rules:

- no nested domain-specific settings prefixes
- no alternate `/api/runtime/settings` or `/api/system/settings` variants
- `PUT /api/settings` is reserved but non-persistent until a safe write flow exists

## Capability-first UI behavior

Settings and similar operational pages must report capability state instead of
showing raw HTTP errors as the main UX.

Supported capability states:

- `READY`
- `PARTIAL`
- `NOT_IMPLEMENTED`

Implications:

- UI routes must remain navigable even when the backend capability is missing
- backend absence or mismatch must degrade into a safe capability summary
- sidebar navigation must not depend on backend reachability
- write actions must stay disabled until the backend exposes a safe mutation contract

## Current settings page behavior

The Settings page is currently read-only and renders:

- a top-level capability summary
- a capability matrix for read/schema/update support
- a structured configuration tree from `GET /api/settings`

Current safety boundary:

- the backend exposes configuration inspection only
- no settings persistence is implemented
- the UI must not claim write readiness

## Runtime page behavior

The Runtime page must:

- show physical file findings and metadata diagnostics separately
- distinguish file-level damage from job-level failure
- keep unexplained or unsupported states visible
- never encourage blind retries when corruption, truncation, missing files, or
  permission errors are already proven

## Backup contract

The backup UI must treat backend state as the source of truth for:

- background size estimation
- manual target inventory
- target validation state
- manual backup execution state
- verification level
- restore-readiness signaling

Canonical backup endpoints now include:

```text
GET /api/backup/snapshots
GET /api/backup/size-estimate
POST /api/backup/size-estimate/collect
GET /api/backup/targets
POST /api/backup/targets
PUT /api/backup/targets/{target_id}
DELETE /api/backup/targets/{target_id}
GET /api/backup/targets/{target_id}/validation
POST /api/backup/targets/{target_id}/validate
GET /api/backup/executions/current
POST /api/backup/executions
POST /api/backup/executions/cancel
```

Backup UI rules:

- never show restore-ready or disaster-recovery-ready wording unless the backend says so
- files-only backup must stay labeled as files-only
- path-like execution must stay distinct from transport-prepared SSH/rsync snapshot transfer and from unsupported SMB `system_mount` targets
- target forms must hide irrelevant fields for the selected mode instead of exposing one generic transport superset
- SMB `pre_mounted_path` must be presented as a mounted local path, not as a full SMB transport form
- SSH shorthand may be primary, but separate host/user/port fields must stay visually secondary
- rsync wording must stay explicit that the current target type is rsync over SSH
- target warnings must be visible before execution
- verification labels must describe the actual assurance level and must not imply end-to-end integrity proof
- snapshot cards must describe manifest-structure status separately from artifact-content verification
- pending, running, partial, failed, unsupported, and canceled states must remain visible
- secret inputs may be sent to the backend on create/update, but UI state and later reads must only show secret references and never masked secret echoes
- source size estimate must expose whether the shown value is unknown, stale, queued, running, partial, completed, failed, or unsupported
- source size estimate values from before the current doctor restart must not be presented as fresh
- source size estimate must trigger a recalculation on startup and must expose a manual refresh action that stays disabled while a run is active

Canonical backup machine values and UI/doc meanings:

- job state `pending`: queued or not yet started; never implies data was collected
- job state `running`: actively collecting, validating, or transferring
- job state `partial`: finished with only partial data, partial validation coverage, or warnings that materially limit confidence
- job state `completed`: finished successfully for the currently implemented scope only; never implies restore-readiness
- job state `failed`: finished unsuccessfully
- job state `unsupported`: current implementation cannot safely cover the requested configuration or scope
- job state `cancel_requested`: cancellation was requested but the job has not reached a terminal state yet
- job state `canceled`: the job stopped after cancellation
- backup coverage `files_only`: file scope only; use the human label `files-only`
- verification level `none`: no verification beyond task outcome
- verification level `transport_success_only`: the transfer process reported success
- verification level `destination_exists`: destination existence was checked in addition to transport success
- verification level `basic_manifest_verified`: only manifest structure checks passed
- restore readiness `not_implemented`: no restore execution is available
- restore readiness `partial`: some restore planning/readiness signals exist, but no full restore guarantee exists
- snapshot basic validity `valid`: manifest structure is valid
- snapshot basic validity `invalid`: manifest structure is invalid

Terminology rules:

- `ready` in target verification status means validated for currently implemented checks only
- `snapshot` means a persisted backup record with manifest metadata; it is not automatically a full restore point
- `manifest` means the persisted JSON metadata record; it is not artifact-content verification
- `stale` means cached size-estimate data is older than the freshness window and should be treated as aged data
- size-estimate status `unknown`: no current estimate is available yet
- size-estimate status `queued`: a recalculation was requested but has not started execution yet
- size-estimate status `running`: a recalculation is in progress
- size-estimate status `stale`: the shown value is from an older collection and must not be treated as fresh, including values from before the current doctor restart

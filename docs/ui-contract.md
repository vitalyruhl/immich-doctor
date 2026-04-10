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

## Missing asset references page

The missing-asset-reference UI must stay review-first and mutation-last.

Canonical behavior:

- show findings for `public.asset.originalPath` only
- keep `present`, `missing_on_disk`, `permission_error`, `unreadable_path`, `unsupported`, and `already_removed` distinct in the table
- label only `missing_on_disk` with `ready` repair readiness as selectable for removal
- show the repair scope explicitly, including the asset table and the supported restore tables
- keep preview separate from apply
- show the exact preview set before apply
- refuse apply when the previewed scan state drifted materially
- surface restore points as separate records with restore and delete as separate actions
- make delete of restore points a distinct confirmation path

UI safety gate:

- before apply, the UI must warn that both database and asset/storage backups should exist
- apply must stay disabled until the operator checks:
  - `I have read the warning`
  - `I created a backup`
- the disclaimer gate is UI-only and does not replace CLI flags or backend validation

Recovery limits shown in UI:

- restore points only contain the database reference state captured during apply
- restore points do not recreate missing files
- unsupported schema mappings remain blocked and must be reported clearly
- already removed rows should be shown as such instead of being hidden

## Catalog-backed remediation UI

The catalog-backed consistency page now also exposes explicit remediation review
for cached storage-vs-DB mismatch classes.

Canonical behavior:

- render broken DB originals, zero-byte files, and `.fuse_hidden*` storage orphans as separate sections
- keep checkbox selection explicit per section
- support single-item, selected-items, and all-eligible preview flows
- keep preview separate from apply
- only enable apply after preview plus explicit confirmation checkboxes
- keep item typing explicit in the UI state and API payloads

Broken DB original rules:

- show `missing_confirmed`, `found_elsewhere`, `found_with_hash_match`, and `unresolved_search_error` as distinct badges
- show expected DB path and found path for `found_elsewhere`
- explain that `found_elsewhere` is not auto-deleted because the file may still exist elsewhere
- show checksum-verification state for path-mismatch candidates when available
- expose destructive cleanup only for `missing_confirmed`
- expose explicit DB path-fix only for `found_with_hash_match`

Zero-byte rules:

- `.immich` must not be rendered as a remediation candidate
- show `zero_byte_upload_orphan`, `zero_byte_upload_critical`, `zero_byte_video_derivative`, and `zero_byte_thumb_derivative` as distinct badges
- explain that `zero_byte_upload_critical` is still referenced as an original and therefore not deletable by default
- expose explicit delete apply only for orphan or derivative classes
- make clear that derivative deletion is a cleanup step, not an implicit regenerate step

`.fuse_hidden*` orphan rules:

- `.immich` must not be rendered as a repair candidate
- show `blocked_in_use`, `deletable_orphan`, and `check_failed` as distinct badges
- explain that `blocked_in_use` cannot be removed safely yet
- expose delete apply only for `deletable_orphan`
- if the in-use check is unavailable, surface the backend reason instead of faking readiness

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
- SSH validation must report the final backend result instead of leaving the UI in a stale running state
- SSH validation failures must expose an actionable summary from the backend, for example missing `SSH_AUTH_SOCK` in the doctor runtime or an unwritable remote destination
- SSH validation success must stay distinct from rsync-based remote execution readiness; missing local `rsync` must surface as an execution limitation, not as a generic target failure
- backup UI must explain that SSH agent auth uses a forwarded host SSH agent in the container runtime
- backup UI must explain that host SSH success and host known_hosts trust do not automatically carry into the container
- backup UI must keep username-plus-auth-material expectations explicit; username alone is never valid SSH auth
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
- SMB `system_mount` must stay labeled as planned or unsupported until doctor can actually mount and use it end to end
- `snapshot` means a persisted backup record with manifest metadata; it is not automatically a full restore point
- `manifest` means the persisted JSON metadata record; it is not artifact-content verification
- `stale` means cached size-estimate data is older than the freshness window and should be treated as aged data
- size-estimate status `unknown`: no current estimate is available yet
- size-estimate status `queued`: a recalculation was requested but has not started execution yet
- size-estimate status `running`: a recalculation is in progress
- size-estimate status `stale`: the shown value is from an older collection and must not be treated as fresh, including values from before the current doctor restart

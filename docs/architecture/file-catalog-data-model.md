# File Catalog Data Model Draft

## Purpose

This draft defines the candidate entities and relationships for the persistent
file inventory redesign. It is intentionally detailed enough for implementation
planning, but not every field is final.

## Modeling goals

- represent a durable current file catalog
- preserve scan-session and snapshot boundaries
- support resumable scanning
- support DB correlation without repeated filesystem walks
- layer derivative and deep-integrity results on top of the same catalog
- support quarantine, restore, and audit trails

## Proposed entities

### `storage_root`

Represents one configured filesystem root that can be scanned and normalized.

Candidate fields:

- `id`
- `slug`
- `display_name`
- `root_type`
  Examples: `source`, `thumbs`, `encoded`, `quarantine`
- `absolute_path`
- `path_case_sensitive`
- `enabled`
- `created_at`
- `updated_at`

Important constraints:

- unique `slug`
- unique `absolute_path`

### `scan_session`

Represents one execution attempt that may be resumed.

Candidate fields:

- `id`
- `storage_root_id`
- `session_type`
  Examples: `inventory_full`, `inventory_incremental`, `integrity_deep`
- `status`
  Examples: `planned`, `running`, `paused`, `completed`, `failed`, `abandoned`
- `requested_by`
- `started_at`
- `heartbeat_at`
- `completed_at`
- `resume_token`
- `checkpoint_path`
- `last_relative_path`
- `directories_completed`
- `files_seen`
- `bytes_seen`
- `error_count`
- `notes_json`

Indexes:

- `(storage_root_id, status)`
- `(storage_root_id, started_at DESC)`

### `scan_checkpoint`

Explicit checkpoint rows may be separate from `scan_session` if progress writes
need to be append-friendly.

Candidate fields:

- `id`
- `scan_session_id`
- `sequence_no`
- `checkpoint_path`
- `last_relative_path`
- `directories_completed`
- `files_seen`
- `bytes_seen`
- `recorded_at`
- `state_json`

Indexes:

- `(scan_session_id, sequence_no DESC)`

### `scan_snapshot`

Represents a committed generation boundary used by downstream analysis.

Candidate fields:

- `id`
- `storage_root_id`
- `source_scan_session_id`
- `snapshot_kind`
  Examples: `inventory`, `db_reference_import`, `integrity_layer`
- `generation`
- `status`
  Examples: `committed`, `superseded`, `failed`
- `based_on_snapshot_id`
- `started_at`
- `committed_at`
- `item_count`
- `zero_byte_count`
- `notes_json`

Indexes:

- `(storage_root_id, generation DESC)`
- `(storage_root_id, status, committed_at DESC)`

### `file_record`

One logical file row per normalized relative path within a storage root.

Candidate fields:

- `id`
- `storage_root_id`
- `relative_path`
- `canonical_path`
  Optional absolute normalized path for current runtime only
- `parent_relative_path`
- `file_name`
- `extension`
- `size_bytes`
- `created_at_fs`
- `modified_at_fs`
- `first_seen_at`
- `last_seen_at`
- `first_seen_snapshot_id`
- `last_seen_snapshot_id`
- `last_scan_session_id`
- `file_type_guess`
- `media_class_guess`
- `zero_byte_flag`
- `stat_device`
- `stat_inode`
- `hash_status`
  Examples: `not_requested`, `queued`, `computed`, `failed`
- `content_hash`
- `hash_algorithm`
- `hash_last_verified_at`
- `presence_status`
  Examples: `present`, `not_seen_in_latest_snapshot`, `quarantined`
- `metadata_json`

Required uniqueness:

- unique `(storage_root_id, relative_path)`

Important indexes:

- `(storage_root_id, last_seen_snapshot_id)`
- `(storage_root_id, zero_byte_flag, last_seen_snapshot_id)`
- `(storage_root_id, extension)`
- `(storage_root_id, modified_at_fs)`

Notes:

- `relative_path` is the authoritative join key for Phase 1 and Phase 2.
- `stat_device` and `stat_inode` are hints only. They are not portable enough
  to be the primary identity.
- `canonical_path` is optional because mounted absolute paths may differ across
  deployments.

### Optional extension: `file_observation`

If implementation later needs stronger historical replay than
`first_seen_snapshot_id` and `last_seen_snapshot_id`, add a sparse observation
table rather than duplicating the full file row each snapshot.

Candidate fields:

- `snapshot_id`
- `file_record_id`
- `size_bytes`
- `modified_at_fs`
- `observed_at`

This is optional in the first implementation.

### `db_asset_reference`

Normalized Immich DB references imported into the catalog for correlation.

Candidate fields:

- `id`
- `snapshot_id`
- `asset_id`
- `asset_file_id`
- `reference_role`
  Examples: `source`, `preview`, `thumbnail`, `encoded`
- `storage_root_id`
- `absolute_path_raw`
- `normalized_relative_path`
- `normalization_status`
  Examples: `resolved`, `outside_registered_root`, `invalid_path`
- `source_table`
- `source_column`
- `owner_asset_id`
- `discovered_at`
- `metadata_json`

Indexes:

- `(snapshot_id, storage_root_id, normalized_relative_path)`
- `(asset_id, reference_role)`
- `(normalization_status)`

### `correlation_result`

Represents the outcome of joining catalog rows and DB references.

Candidate fields:

- `id`
- `snapshot_id`
- `storage_root_id`
- `result_class`
  Examples: `db_missing_on_disk`, `disk_orphan`, `db_reference_outside_scope`
- `status`
  Examples: `open`, `reviewed`, `quarantined`, `resolved`, `dismissed`
- `file_record_id`
- `db_asset_reference_id`
- `severity`
- `confidence`
- `reason_code`
- `details_json`
- `created_at`
- `resolved_at`

Indexes:

- `(snapshot_id, result_class, status)`
- `(file_record_id)`
- `(db_asset_reference_id)`

### `derivative_candidate`

Tracks leftover derivatives and other non-primary file candidates.

Candidate fields:

- `id`
- `snapshot_id`
- `file_record_id`
- `storage_root_id`
- `derivative_kind`
  Examples: `thumbnail`, `preview`, `encoded_output`, `unknown_derivative`
- `owner_asset_id`
- `owner_reference_id`
- `detection_rule`
- `confidence`
  Examples: `safe`, `likely`, `uncertain`
- `safe_action_class`
  Examples: `report_only`, `quarantine_candidate`
- `status`
  Examples: `open`, `reviewed`, `quarantined`, `dismissed`
- `details_json`
- `created_at`

Indexes:

- `(snapshot_id, derivative_kind, confidence)`
- `(file_record_id)`

### `integrity_check_result`

Stores layered integrity work without redefining file identity.

Candidate fields:

- `id`
- `snapshot_id`
- `file_record_id`
- `check_kind`
  Examples: `basic_read_probe`, `image_decode`, `ffprobe`, `checksum`
- `status`
  Examples: `ok`, `missing`, `zero_byte`, `corrupted`, `permission_denied`, `failed`
- `tool_name`
- `tool_version`
- `result_code`
- `message`
- `details_json`
- `started_at`
- `completed_at`
- `attempt_no`

Indexes:

- `(file_record_id, check_kind, completed_at DESC)`
- `(snapshot_id, status)`

### `quarantine_entry`

Represents one quarantined file and its recovery metadata.

Candidate fields:

- `id`
- `operation_id`
- `repair_run_id`
- `file_record_id`
- `correlation_result_id`
- `source_snapshot_id`
- `storage_root_id`
- `source_relative_path`
- `source_absolute_path_at_move`
- `quarantine_relative_path`
- `quarantine_absolute_path`
- `reason_code`
- `correlation_class`
- `db_asset_id`
- `asset_file_id`
- `checksum`
- `size_bytes`
- `moved_at`
- `restore_status`
  Examples: `available`, `restored`, `failed_restore`
- `sidecar_version`
- `details_json`

Indexes:

- `(repair_run_id, moved_at DESC)`
- `(storage_root_id, source_relative_path)`
- `(restore_status)`

### `operation_journal`

Append-only action history. The SQLite table mirrors durable JSONL journal data,
but JSONL remains the recovery-safe external trail.

Candidate fields:

- `id`
- `operation_id`
- `repair_run_id`
- `event_sequence`
- `event_type`
  Examples: `plan_created`, `copy_started`, `copy_verified`, `source_removed`,
  `restore_started`, `restore_completed`, `failed`
- `subject_type`
  Examples: `file_record`, `quarantine_entry`, `correlation_result`
- `subject_id`
- `payload_json`
- `created_at`
- `actor`

Indexes:

- `(operation_id, event_sequence)`
- `(repair_run_id, created_at)`

## Relationships

Recommended relationship outline:

- `storage_root 1 -> many scan_session`
- `storage_root 1 -> many scan_snapshot`
- `storage_root 1 -> many file_record`
- `scan_session 1 -> many scan_checkpoint`
- `scan_session 1 -> 0..1 committed scan_snapshot`
- `scan_snapshot 1 -> many db_asset_reference`
- `file_record 1 -> many integrity_check_result`
- `file_record 1 -> many derivative_candidate`
- `file_record 1 -> many correlation_result`
- `file_record 1 -> many quarantine_entry`
- `quarantine_entry 1 -> many operation_journal`

## Snapshot strategy

Recommended first implementation:

- keep a current-state `file_record` table
- track snapshot boundaries through `first_seen_snapshot_id` and
  `last_seen_snapshot_id`
- avoid full snapshot duplication until a concrete need for historical replay
  appears

This keeps the large-library footprint lower while still enabling staged
analysis.

## Phase 1 minimum viable schema

The first implementation does not need every table above. Minimum recommended
tables:

- `storage_root`
- `scan_session`
- `scan_checkpoint`
- `scan_snapshot`
- `file_record`

Phase 2 adds:

- `db_asset_reference`
- `correlation_result`

Phase 3 adds:

- `derivative_candidate`

Phase 4 adds:

- `quarantine_entry`
- `operation_journal`

Phase 5 adds:

- `integrity_check_result`

## Open modeling questions

1. Should snapshot retention keep multiple committed generations per root from
   day one?
2. Should `file_observation` exist in the first release for stronger historical
   replay, or only after catalog-size measurements?
3. Should checksum storage be generic in `file_record`, or deferred entirely to
   `integrity_check_result`?


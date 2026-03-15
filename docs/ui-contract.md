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

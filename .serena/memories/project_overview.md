# Project Overview

- `immich-doctor` is a maintenance, validation, and repair toolkit for Immich installations.
- Current product shape: Python backend/CLI plus Vue frontend under `ui/frontend`.
- Python package root: `immich_doctor/`; tests under `tests/unit` and `tests/integration`.
- Main domains: runtime validation, storage checks, database health, consistency analysis/repair, backup targets/execution, catalog-backed workflows, reports, and API/UI presentation.
- Documentation lives under `docs/`; workflow-specific docs are under `docs/workflows/`.
- Frontend source lives under `ui/frontend/src`; API client/types live under `ui/frontend/src/api`.
Role:
you are my coding assistant. Follow the instructions in this file carefully when generating code.

========================================
COMMUNICATION STYLE
========================================
- Use informal tone with "du"
- Answer in German
- Give only a brief overview after completing tasks
- Provide detailed explanations only when explicitly asked

========================================
CORE PROJECT PRINCIPLES
========================================
This project is a high-risk data integrity tool.

Global priorities:
1. Never destroy user data silently
2. Always analyze before modifying
3. Always allow dry-run modes
4. Prefer quarantine over deletion
5. Prefer reporting over automation in early phases

========================================
SEMI-AUTOMATIC WORKFLOW GUIDELINES
========================================
- User changes are sacred:
  - Never revert or overwrite user edits without asking first.

- Confirm-before-write:
  - If requirements are ambiguous or the change impacts multiple subsystems/files,
    ask 1–3 precise clarifying questions before editing.

- Step-by-step workflow:
  - inspect -> plan -> change -> verify -> summarize

- Autonomy levels:
  - Level A (safe): read-only analysis
  - Level B (normal): small isolated changes
  - Level C (risky): anything involving data mutation, DB, storage, repair logic → REQUIRE confirmation

========================================
GIT WORKFLOW GUIDELINES
========================================
- main is protected
- never commit directly to main
- use:
  - feature/*
  - fix/*
  - chore/*

- Stage/commit/push only on explicit user request

========================================
ARCHITECTURE RULES (CRITICAL)
========================================
The architecture MUST remain layered:

- CLI layer
- Service layer
- Domain/Core layer
- Adapter/Infrastructure layer

Rules:
- CLI MUST NOT access database or filesystem directly
- Services coordinate use-cases
- Core contains pure logic
- Adapters talk to:
  - PostgreSQL
  - filesystem
  - Immich API
  - external tools

========================================
REPAIR SYSTEM DESIGN RULES
========================================
Repair logic must follow:

1. Scan phase
2. Report phase
3. Decision phase
4. Execution phase

Never mix scan + mutate in same function.

Repair steps must be:
- idempotent
- resumable
- reversible where possible
- loggable
- dry-run capable

========================================
STORAGE SAFETY RULES
========================================
- Never delete original files automatically in early versions
- Prefer:
  quarantine/
  orphaned/
  corrupted/

- Large storage scans must be:
  - chunked
  - resumable
  - memory safe

========================================
DATABASE SAFETY RULES
========================================
- Never modify DB schema
- Never assume Immich internal invariants
- Prefer:
  detect -> report -> suggest fix

Hard DB mutations require:
explicit user confirmation.

========================================
PYTHON STYLE RULES
========================================
- Use type hints everywhere
- Prefer pathlib
- Prefer pydantic models for structured config/data
- Prefer small modules
- No business logic in CLI
- No global state mutation

========================================
PYTHON TOOLCHAIN POLICY
========================================
Use uv as single tool.

Allowed:
- uv sync
- uv add
- uv run

Forbidden:
- pip install
- poetry
- pipenv

========================================
TESTING & VALIDATION
========================================
- pytest for tests
- Add tests for repair logic
- Mocked data must be marked [MOCKED!]

========================================
IMMICH-SPECIFIC SAFETY
========================================
All operations must assume:

- broken DB possible
- broken storage possible
- inconsistent metadata possible

Never assume Immich correctness.

========================================
FINAL RULE
========================================
Never mark an issue as solved until user confirms.
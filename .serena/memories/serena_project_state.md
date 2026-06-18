# Serena Project State

- Stable Serena project configuration is intended to be tracked: `.serena/project.yml` and shared memories under `.serena/memories/*.md`.
- `.serena/project.yml` intentionally keeps `included_optional_tools` and `fixed_tools` empty for the Codex context; Codex file and shell operations stay with Codex' native tools, while Serena provides symbolic/code-intelligence tools. The project is Python with UTF-8 encoding.
- Local-only Serena state is ignored from the root `.gitignore`: `.serena/project.local.yml`, cache/index/log/tmp folders, and local/tmp memories.
- Do not add a separate `.serena/.gitignore` unless the root `.gitignore` approach becomes insufficient.
- Never delete `.serena/` wholesale during cleanup. If cleanup is needed, delete only known ignored runtime paths after checking `git status --short --ignored` and `git check-ignore -v`.
- Shared memories should contain durable, non-secret project conventions. Personal notes, temporary task notes, and machine-specific details belong in ignored local/tmp memory paths.
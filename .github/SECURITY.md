# Security Policy

## Supported versions

This repository does not have a stable production release yet.

Until the first stable release is published:

- the latest `main` branch state is the active hardening target
- security fixes should be prepared in pull requests and merged through normal review
- users should assume the project is experimental and validation-focused

## Reporting a vulnerability

If you believe you found a security vulnerability:

1. Do not open a public issue with exploit details.
2. Prefer GitHub private vulnerability reporting if it is enabled for the repository.
3. If private reporting is not enabled yet, contact the repository owner privately before public disclosure.

Public GitHub issues are appropriate for:

- general hardening suggestions
- non-sensitive dependency updates
- documentation improvements
- safe-by-design review requests

## Response expectations

The project aims to:

- acknowledge reports in a reasonable time
- assess impact and exploitability
- coordinate a fix before full public disclosure when appropriate
- document any important mitigation or upgrade guidance

## Scope

Security-relevant areas include:

- CLI input handling
- environment and secret handling
- database connection handling
- Docker and Compose configuration
- future repair or quarantine workflows
- GitHub workflow and release process integrity

## Project-specific safety notes

This project is intentionally conservative:

- backup first
- analyze before repair
- quarantine before delete
- dry-run before apply

Any future feature that can delete, move, rewrite, or quarantine user data should
be treated as both a safety-sensitive and security-relevant change.

# Development

## Local setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .[dev]
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

## Useful commands

```bash
python -m immich_doctor --help
python -m immich_doctor health ping
python -m immich_doctor config validate --output json
python -m immich_doctor backup validate
pytest
ruff check .
```

## Development expectations

- keep changes small
- keep service boundaries clean
- add tests with behavior changes
- update docs when scope or configuration changes


from __future__ import annotations

import re
import tomllib
from pathlib import Path

from immich_doctor import __version__
from immich_doctor.api.app import create_api_app


def test_project_metadata_module_and_api_share_version() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version_module = Path("immich_doctor/version.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', version_module, re.MULTILINE)

    assert match is not None
    assert "version" not in pyproject["project"]
    assert pyproject["project"]["dynamic"] == ["version"]
    assert pyproject["tool"]["hatch"]["version"]["path"] == "immich_doctor/version.py"
    assert __version__ == match.group(1)
    assert create_api_app().version == match.group(1)

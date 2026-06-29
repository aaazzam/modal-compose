from __future__ import annotations

from pathlib import Path

import pytest

from modal_compose.cli import init

pytestmark = pytest.mark.unit

ROOT_FILES = {"pyproject.toml", "README.md", "devbox"}
PACKAGE_FILES = {
    "__init__.py",
    "api.py",
    "registry.py",
    "services.py",
    "server.py",
    "toolbox.py",
    "tools",
}


class TestInit:
    def test_scaffolds_a_runnable_project(self, tmp_path: Path) -> None:
        init(tmp_path)
        assert ROOT_FILES <= {p.name for p in tmp_path.iterdir()}
        assert {p.name for p in (tmp_path / "devbox").iterdir()} == PACKAGE_FILES

    def test_refuses_to_overwrite_without_force(self, tmp_path: Path) -> None:
        init(tmp_path)
        with pytest.raises(SystemExit, match="already has"):
            init(tmp_path)

    def test_does_not_clobber_an_unrelated_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("mine")
        with pytest.raises(SystemExit, match="pyproject.toml"):
            init(tmp_path)
        assert (tmp_path / "pyproject.toml").read_text() == "mine"

    def test_force_overwrites_existing_files(self, tmp_path: Path) -> None:
        init(tmp_path)
        (tmp_path / "devbox" / "api.py").write_text("stale")
        init(tmp_path, force=True)
        assert (tmp_path / "devbox" / "api.py").read_text() != "stale"

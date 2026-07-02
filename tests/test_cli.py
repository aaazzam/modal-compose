from __future__ import annotations

from pathlib import Path

import pytest

from modal_compose.cli import add, init, list_boxes

pytestmark = pytest.mark.unit

ROOT_FILES = {"pyproject.toml", "README.md", "devbox"}
PACKAGE_FILES = {
    "__init__.py",
    "repos",
    "registry.py",
    "services.py",
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
        (tmp_path / "devbox" / "repos" / "modal.py").write_text("stale")
        init(tmp_path, force=True)
        assert (tmp_path / "devbox" / "repos" / "modal.py").read_text() != "stale"


class TestAdd:
    def test_scaffolds_a_box_module_and_registers_it(self, tmp_path: Path) -> None:
        init(tmp_path)
        add("octocat/widget", directory=tmp_path)

        module = (tmp_path / "devbox" / "repos" / "widget.py").read_text()
        assert 'repo="octocat/widget"' in module
        assert 'DevBox("widget"' in module

        registry = (tmp_path / "devbox" / "registry.py").read_text()
        assert "from .repos import widget" in registry
        assert "registry.add(widget.box)" in registry
        assert "from .repos import modal" in registry

    def test_normalizes_a_github_url(self, tmp_path: Path) -> None:
        init(tmp_path)
        add("https://github.com/octocat/Hello-World.git", directory=tmp_path)
        module = (tmp_path / "devbox" / "repos" / "hello_world.py").read_text()
        assert 'repo="octocat/Hello-World"' in module

    def test_custom_name_and_ref(self, tmp_path: Path) -> None:
        init(tmp_path)
        add("octocat/widget", name="thing", ref="dev", directory=tmp_path)
        module = (tmp_path / "devbox" / "repos" / "thing.py").read_text()
        assert 'ref="dev"' in module

    def test_requires_an_initialized_project(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="modal-compose init"):
            add("octocat/widget", directory=tmp_path)

    def test_refuses_to_overwrite_without_force(self, tmp_path: Path) -> None:
        init(tmp_path)
        add("octocat/widget", directory=tmp_path)
        with pytest.raises(SystemExit, match="already exists"):
            add("octocat/widget", directory=tmp_path)

    def test_rejects_a_bad_repo(self, tmp_path: Path) -> None:
        init(tmp_path)
        with pytest.raises(SystemExit, match="owner/name"):
            add("not-a-repo", directory=tmp_path)


class TestListBoxes:
    def test_requires_an_initialized_project(self, tmp_path: Path) -> None:
        with pytest.raises(SystemExit, match="modal-compose init"):
            list_boxes(directory=tmp_path)

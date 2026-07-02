from __future__ import annotations

import asyncio
import importlib
import sys
from pathlib import Path

import pytest

from modal_compose.cli import init

pytestmark = pytest.mark.integration


@pytest.fixture
def scaffolded(tmp_path: Path):
    init(tmp_path)
    sys.path.insert(0, str(tmp_path))
    yield tmp_path
    for entry in (str(tmp_path), str(tmp_path.resolve())):
        while entry in sys.path:
            sys.path.remove(entry)
    for name in list(sys.modules):
        if name == "devbox" or name.startswith("devbox."):
            del sys.modules[name]


class TestScaffoldedServer:
    def test_registry_registers_the_example_box(self, scaffolded: Path) -> None:
        registry = importlib.import_module("devbox.registry").registry
        assert tuple(registry) == ("modal",)

    def test_added_box_registers_and_imports(self, scaffolded: Path) -> None:
        from modal_compose.cli import add

        add("octocat/widget", directory=scaffolded)
        importlib.invalidate_caches()
        registry = importlib.import_module("devbox.registry").registry
        assert set(registry) == {"modal", "widget"}
        assert registry["widget"].layers[0].repo == "octocat/widget"

    def test_server_exposes_lifecycle_tools(self, scaffolded: Path) -> None:
        mcp = importlib.import_module("devbox.services").mcp

        async def names() -> set[str]:
            return {tool.name for tool in await mcp.list_tools()}

        assert {"create_sandbox", "kill_sandbox"} <= asyncio.run(names())

    def test_server_exposes_the_file_and_shell_tools(self, scaffolded: Path) -> None:
        mcp = importlib.import_module("devbox.services").mcp

        async def names() -> set[str]:
            return {tool.name for tool in await mcp.list_tools()}

        assert {"bash", "edit", "glob", "grep", "read", "write"} <= asyncio.run(names())

    def test_create_sandbox_box_is_generated_from_the_registry(
        self, scaffolded: Path
    ) -> None:
        mcp = importlib.import_module("devbox.services").mcp

        async def schema() -> dict[str, object]:
            tool = await mcp.get_tool("create_sandbox")
            return tool.parameters["properties"]["box"]

        assert asyncio.run(schema())["enum"] == ["modal"]

    def test_list_prints_the_registry(
        self, scaffolded: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from modal_compose.cli import list_boxes

        list_boxes(directory=scaffolded)
        out = capsys.readouterr().out
        assert "modal-compose" in out
        assert "GitHub(modal-labs/modal-client@main)" in out

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from modal_compose import create_server
from modal_compose.layer import Layer, Repo
from modal_compose.registry import Registry

from .conftest import FakeImage, StubRemote

pytestmark = pytest.mark.unit


def _registry(*names: str) -> Registry:
    registry = Registry(base_image=FakeImage())
    for name in names:
        source = StubRemote(working_directory=f"/{name}")
        registry.mount(name, Repo(layers=[Layer(name=name, source=source)]))
    return registry


def _tool_names(mcp: Any) -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


class TestCreateServer:
    def test_exposes_lifecycle_and_file_tools(self) -> None:
        names = _tool_names(create_server(_registry("demo")))
        assert {"create_sandbox", "kill_sandbox"} <= names
        assert {"bash", "edit", "glob", "grep", "read", "write"} <= names

    def test_create_sandbox_enum_comes_from_the_registry(self) -> None:
        mcp = create_server(_registry("alpha", "beta"))

        async def repo_schema() -> dict[str, Any]:
            tool = await mcp.get_tool("create_sandbox")
            return tool.parameters["properties"]["repo"]

        assert asyncio.run(repo_schema())["enum"] == ["alpha", "beta"]

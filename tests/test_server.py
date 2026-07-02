from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastmcp import FastMCP
from modal import Sandbox

from modal_compose import DevBox, DevBoxProvider, Layer, Registry, create_server
from modal_compose import server as server_module

from .conftest import FakeImage

pytestmark = pytest.mark.unit


def _registry(*names: str, registry_name: str = "modal-compose") -> Registry:
    registry = Registry(registry_name, base_image=FakeImage())
    for name in names:
        registry.add(DevBox(name, layers=[Layer(workdir=f"/{name}")]))
    return registry


def _tool_names(mcp: Any) -> set[str]:
    return {tool.name for tool in asyncio.run(mcp.list_tools())}


class _Aio:
    def __init__(self, fn: Any) -> None:
        self._fn = fn

    async def aio(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)


class FakeTaggedSandbox:
    def __init__(self, tags: dict[str, str]) -> None:
        self.tags = tags
        self.terminated = False
        self.get_tags = _Aio(lambda: self.tags)
        self.terminate = _Aio(self._terminate)

    def _terminate(self) -> None:
        self.terminated = True


class FakeModal:
    def __init__(self, sandbox: FakeTaggedSandbox) -> None:
        class _Sandbox:
            from_id = _Aio(lambda sandbox_id: sandbox)

        self.Sandbox = _Sandbox


class TestCreateServer:
    def test_exposes_lifecycle_and_file_tools(self) -> None:
        names = _tool_names(create_server(_registry("demo")))
        assert {"create_sandbox", "kill_sandbox"} <= names
        assert {"bash", "edit", "glob", "grep", "read", "write"} <= names

    def test_name_defaults_to_the_registry_name(self) -> None:
        mcp = create_server(_registry("demo", registry_name="acme-dev"))
        assert mcp.name == "acme-dev"

    def test_explicit_name_wins(self) -> None:
        mcp = create_server(_registry("demo"), name="my-server")
        assert mcp.name == "my-server"

    def test_create_sandbox_enum_comes_from_the_registry(self) -> None:
        mcp = create_server(_registry("alpha", "beta"))

        async def box_schema() -> dict[str, Any]:
            tool = await mcp.get_tool("create_sandbox")
            return tool.parameters["properties"]["box"]

        assert asyncio.run(box_schema())["enum"] == ["alpha", "beta"]


class TestDevBoxProvider:
    def test_mounts_on_a_caller_owned_server(self) -> None:
        mcp = FastMCP("mine", providers=[DevBoxProvider(_registry("demo"))])
        names = _tool_names(mcp)
        assert {"create_sandbox", "kill_sandbox", "bash", "read"} <= names
        assert mcp.name == "mine"


class TestKillSandbox:
    def _kill(self, registry: Registry, sandbox: FakeTaggedSandbox) -> str:
        mcp = create_server(registry)

        async def run() -> Any:
            tool = await mcp.get_tool("kill_sandbox")
            return await tool.run({"sandbox_id": "sb-123"})

        return asyncio.run(run())

    def test_runs_terminate_hooks_before_killing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events: list[str] = []

        class Web(Layer):
            def on_terminate(self, sandbox: Sandbox) -> None:
                events.append("hook")

        registry = Registry(base_image=FakeImage())
        registry.add(DevBox("web", layers=[Web()]))
        sandbox = FakeTaggedSandbox({"box": "web", "run": "r-1"})
        monkeypatch.setattr(server_module, "modal", FakeModal(sandbox))

        self._kill(registry, sandbox)

        assert events == ["hook"]
        assert sandbox.terminated is True

    def test_rejects_a_sandbox_without_a_box_tag(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _registry("web")
        sandbox = FakeTaggedSandbox({})
        monkeypatch.setattr(server_module, "modal", FakeModal(sandbox))

        with pytest.raises(Exception, match="not created by this server"):
            self._kill(registry, sandbox)
        assert sandbox.terminated is False

    def test_rejects_a_sandbox_from_an_unknown_box(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = _registry("web")
        sandbox = FakeTaggedSandbox({"box": "stranger"})
        monkeypatch.setattr(server_module, "modal", FakeModal(sandbox))

        with pytest.raises(Exception, match="not created by this server"):
            self._kill(registry, sandbox)
        assert sandbox.terminated is False

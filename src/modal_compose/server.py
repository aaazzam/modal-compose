from pathlib import Path
from typing import Annotated, Any, Callable, Concatenate, ParamSpec

import modal
from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider, Provider
from mcp.types import ToolAnnotations
from modal.exception import NotFoundError
from pydantic import Field

from .engine import Engine
from .registry import Registry

TOOLS_DIR = Path(__file__).parent / "tools"

P = ParamSpec("P")


def _forwards_fastmcp(
    _factory: Callable[P, FastMCP],
) -> Callable[[Callable[..., FastMCP]], Callable[Concatenate[Registry, P], FastMCP]]:
    def decorate(
        impl: Callable[..., FastMCP],
    ) -> Callable[Concatenate[Registry, P], FastMCP]:
        return impl

    return decorate


@_forwards_fastmcp(FastMCP)
def create_server(registry: Registry, *args: Any, **kwargs: Any) -> FastMCP:
    """Assemble the dev-box MCP server for a registry.

    Every keyword argument of `FastMCP(...)` is forwarded through with its real
    type — `name`, `instructions`, `auth`, `middleware`, `providers`, and the
    rest — so the server's name comes from FastMCP's native `name=`. The file
    and shell tools are auto-discovered from the library's `tools/` via a
    `FileSystemProvider`; a caller `providers=` is merged after it rather than
    replacing it. The `create_sandbox` / `kill_sandbox` lifecycle tools are
    wired here; only `create_sandbox` needs the registry, both to resolve a
    dev-box name to its image and to generate its `box` enum.
    """
    own_providers: list[Provider] = [FileSystemProvider(TOOLS_DIR)]
    caller_providers = kwargs.pop("providers", None) or []
    mcp: FastMCP = FastMCP(*args, providers=[*own_providers, *caller_providers], **kwargs)
    app_name = mcp.name or "modal-compose"

    async def create_sandbox(
        box: Annotated[
            str,
            Field(
                description="Registered dev-box to launch.",
                json_schema_extra={"enum": list(registry.names())},
            ),
        ],
    ) -> str:
        """Create a sandbox for a registered dev-box and return its sandbox_id.

        The box's prebaked named image is used when available; otherwise the
        image is built on the request path and published for next time.
        """
        app = await modal.App.lookup.aio(app_name, create_if_missing=True)
        engine = Engine.from_registry(registry, box, app)
        try:
            run = await engine.create(image=modal.Image.from_name(box))
        except NotFoundError:
            built = await engine.build()
            run = await engine.create(image=built)
        return run.sandbox_id

    mcp.tool(
        create_sandbox,
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, openWorldHint=True
        ),
    )

    async def kill_sandbox(
        sandbox_id: Annotated[str, Field(description="The sandbox_id to kill.")],
    ) -> str:
        """Terminate a sandbox and return its id."""
        sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
        await sandbox.terminate.aio()
        return sandbox_id

    mcp.tool(kill_sandbox, annotations=ToolAnnotations(destructiveHint=True))

    return mcp

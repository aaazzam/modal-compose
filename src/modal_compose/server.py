from collections.abc import Callable, Coroutine, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import modal
from fastmcp import FastMCP
from fastmcp.server.providers import (
    AggregateProvider,
    FileSystemProvider,
    LocalProvider,
    Provider,
)
from mcp.types import ToolAnnotations
from modal.exception import NotFoundError
from pydantic import Field

from .engine import Engine, terminate_sandbox
from .registry import Registry

if TYPE_CHECKING:
    from fastmcp.server.auth import AuthProvider
    from fastmcp.server.middleware import Middleware

TOOLS_DIR = Path(__file__).parent / "tools"


class DevBoxProvider(AggregateProvider):
    """A FastMCP provider exposing a registry's dev-box tools.

    Mount it on any FastMCP server — `FastMCP(..., providers=[DevBoxProvider(registry)])`
    — to add the `create_sandbox` / `kill_sandbox` lifecycle tools plus the
    bundled file and shell tools (`bash`, `edit`, `glob`, `grep`, `read`,
    `write`). Sandboxes run in the Modal app named by `registry.name`, launch
    from the registry's prebaked namespaced images, and `kill_sandbox` refuses
    sandboxes this registry did not create.
    """

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        local = LocalProvider()
        local.tool(
            self._create_sandbox(),
            annotations=ToolAnnotations(
                readOnlyHint=False, destructiveHint=False, openWorldHint=True
            ),
        )
        local.tool(
            self._kill_sandbox(),
            annotations=ToolAnnotations(destructiveHint=True),
        )
        super().__init__(providers=[local, FileSystemProvider(TOOLS_DIR)])

    def _create_sandbox(self) -> Callable[..., Coroutine[Any, Any, str]]:
        registry = self.registry

        async def create_sandbox(
            box: Annotated[
                str,
                Field(
                    description="Registered dev-box to launch.",
                    json_schema_extra={"enum": list(registry)},
                ),
            ],
        ) -> str:
            """Create a sandbox for a registered dev-box and return its sandbox_id.

            The box's prebaked named image is used when available; otherwise the
            image is built on the request path and published for next time —
            expect that cold first launch to take minutes, so retry once with
            a generous timeout if this call times out.
            """
            app = await modal.App.lookup.aio(registry.name, create_if_missing=True)
            engine = Engine.from_registry(registry, box, app)
            try:
                image = modal.Image.from_name(registry.image_name_for(box))
                run = await engine.create(image=image)
            except NotFoundError:
                built = await engine.build()
                run = await engine.create(image=built)
            return run.sandbox_id

        return create_sandbox

    def _kill_sandbox(self) -> Callable[..., Coroutine[Any, Any, str]]:
        registry = self.registry

        async def kill_sandbox(
            sandbox_id: Annotated[str, Field(description="The sandbox_id to kill.")],
        ) -> str:
            """Terminate a sandbox created by `create_sandbox` and return its id.

            Each layer's `on_terminate` hook runs before the sandbox is killed.
            Only sandboxes created from this server's registry can be killed.
            """
            sandbox = await modal.Sandbox.from_id.aio(sandbox_id)
            tags = await sandbox.get_tags.aio()
            name = tags.get("box")
            if name is None or name not in registry:
                raise ValueError(
                    f"sandbox {sandbox_id!r} was not created by this server "
                    f"(no registered dev-box matches its tags)"
                )
            await terminate_sandbox(registry[name], sandbox)
            return sandbox_id

        return kill_sandbox


def create_server(
    registry: Registry,
    *,
    name: str | None = None,
    instructions: str | None = None,
    auth: "AuthProvider | None" = None,
    middleware: "Sequence[Middleware] | None" = None,
    providers: Sequence[Provider] | None = None,
    **fastmcp_settings: Any,
) -> FastMCP:
    """Assemble a FastMCP server serving `registry`'s dev-box tools.

    A convenience over mounting `DevBoxProvider(registry)` on your own
    `FastMCP` server, for when this server's whole job is dev-boxes. `name`
    defaults to `registry.name`; `instructions`, `auth`, and `middleware` are
    FastMCP's own settings, passed through, as is any extra keyword argument
    in `fastmcp_settings`. Caller `providers` are mounted after the dev-box
    provider.
    """
    return FastMCP(
        name=name or registry.name,
        instructions=instructions,
        auth=auth,
        middleware=middleware,
        providers=[DevBoxProvider(registry), *(providers or ())],
        **fastmcp_settings,
    )

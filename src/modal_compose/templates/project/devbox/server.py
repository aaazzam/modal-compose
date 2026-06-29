"""The dev-box MCP server. This file is yours to modify.

The `create_sandbox` / `kill_sandbox` tools are spelled out here rather than
hidden behind a library call, so you can change clone behavior, add tools, or
swap the image strategy. `create_sandbox`'s `repo` argument is generated from
the registry as a `Literal`, so a client may only request repos you mounted.

The file and shell tools (`bash`, `edit`, `glob`, `grep`, `read`, `write`)
live one module each under `tools/` and are auto-discovered by the
`FileSystemProvider`. Drop a module in there to add a tool; delete one to
remove it.

Run it locally over stdio:

    python -m devbox.server

Or deploy it to Modal as an HTTP service:

    modal deploy -m devbox.server
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import modal
from fastmcp import FastMCP
from fastmcp.server.providers import FileSystemProvider
from mcp.types import ToolAnnotations
from modal.exception import NotFoundError
from pydantic import Field

from modal_compose import Engine

from .registry import registry

APP_NAME = "modal-compose"

TOOLS_DIR = Path(__file__).parent / "tools"

mcp: FastMCP = FastMCP(APP_NAME, providers=[FileSystemProvider(TOOLS_DIR)])


async def create_sandbox(
    repo: Annotated[
        str,
        Field(
            description="Registered repo to launch.",
            json_schema_extra={"enum": list(registry.names())},
        ),
    ],
) -> str:
    """Create a sandbox for a registered repo and return its sandbox_id.

    The repo's prebaked named image is used when available; otherwise the image
    is built on the request path and published for next time.
    """
    app = await modal.App.lookup.aio(APP_NAME, create_if_missing=True)
    engine = Engine(
        repo=registry[repo],
        app=app,
        name=repo,
        base_image=registry.base_image,
        secrets=registry.common_secrets,
    )
    try:
        run = await engine.create(image=modal.Image.from_name(repo))
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


deploy_image = (
    modal.Image.debian_slim()
    .pip_install("fastapi", "uvicorn", "pydantic", "fastmcp", "modal")
    .add_local_python_source("modal_compose")
    .add_local_python_source("devbox", ignore=["**/__pycache__", "**/*.pyc"])
)

deploy_app = modal.App("modal-compose-mcp", image=deploy_image)


@deploy_app.function()
@modal.asgi_app()
def serve() -> object:
    return mcp.http_app()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()

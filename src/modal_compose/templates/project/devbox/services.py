"""The dev-box service: the MCP server plus the image-prebake cron, one Modal app.

`create_server` (from `modal_compose`) assembles the MCP server — it
auto-discovers the file and shell tools and wires the `create_sandbox` /
`kill_sandbox` lifecycle tools against your registry. `serve` exposes it over
HTTP, `build_one` builds and publishes one dev-box's named image, and `build`
fans `build_one` out over the registry on a cron (each build an isolated,
retried Modal invocation).

Deploy with `python -m devbox.services` (or `modal deploy -m devbox.services`).
"""

from __future__ import annotations

import modal

from modal_compose import create_server

from .registry import registry

app = modal.App("modal-compose")
image = modal.Image.debian_slim().uv_sync().add_local_python_source("devbox")
mcp = create_server(registry)


@app.function(image=image)
@modal.asgi_app()
def serve() -> object:
    return mcp.http_app(stateless_http=True)


@app.function(image=image, retries=3, timeout=30 * 60)
def build_one(name: str) -> None:
    build_app = modal.App.lookup(app.name, create_if_missing=True)
    built = registry.image_for(name).build(build_app)
    built.publish(name)


@app.function(image=image, schedule=modal.Cron("*/30 * * * *"), timeout=60 * 60)
def build() -> None:
    list(build_one.map(registry.names(), return_exceptions=True))


if __name__ == "__main__":
    app.deploy()

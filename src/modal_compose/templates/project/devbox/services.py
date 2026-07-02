"""The dev-box service: the MCP server plus the image-prebake cron, one Modal app.

`create_server` (from `modal_compose`) assembles the MCP server — it exposes
the file and shell tools and wires the `create_sandbox` / `kill_sandbox`
lifecycle tools against your registry. The Modal app and every published image
are namespaced by `registry.name`, so sandboxes, prebaked images, and the
server all line up. `serve` exposes the server over HTTP, `build_one` builds
and publishes one dev-box's named image, and `build` fans `build_one` out over
the registry on a cron (each build an isolated, retried Modal invocation).

Deploy with `modal-compose deploy` (or `python -m devbox.services`).
"""

from __future__ import annotations

import modal

from modal_compose import create_server

from .registry import registry

app = modal.App(registry.name)
image = modal.Image.debian_slim().uv_sync().add_local_python_source("devbox")
mcp = create_server(registry)


@app.function(image=image)
@modal.asgi_app()
def serve() -> object:
    return mcp.http_app(stateless_http=True)


@app.function(image=image, retries=3, timeout=30 * 60)
def build_one(name: str) -> None:
    build_app = modal.App.lookup(registry.name, create_if_missing=True)
    built = registry.image_for(name).build(build_app)
    built.publish(registry.image_name_for(name))


@app.function(image=image, schedule=modal.Cron("*/30 * * * *"), timeout=60 * 60)
def build() -> None:
    list(build_one.map(list(registry), return_exceptions=True))


if __name__ == "__main__":
    app.deploy()

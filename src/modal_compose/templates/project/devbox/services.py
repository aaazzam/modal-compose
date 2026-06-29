"""Modal app that prebakes a named image per registered repo on a cron.

Deploy with `modal deploy -m devbox.services`. Every half hour each repo in
the registry is built and published under a Modal named image keyed by its
registry name, so the MCP server's `create_sandbox` can launch from a warm
image instead of building on the request path.
"""

from __future__ import annotations

import modal

from .registry import registry

build_image = (
    modal.Image.debian_slim()
    .pip_install("fastapi", "uvicorn", "pydantic")
    .add_local_python_source("devbox", "modal_compose")
)

app = modal.App("modal-compose-build", image=build_image, create_if_missing=True)


@app.function(schedule=modal.Cron("*/30 * * * *"), timeout=30 * 60)
def build_images() -> None:
    for name, repo in registry.items():
        image = repo.get_image(registry.base_image)
        built = image.build(app)
        built.publish(name)

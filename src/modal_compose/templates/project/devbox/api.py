"""A hello-world FastAPI service and the dev-box layer that runs it.

This file is both the application code that runs inside the sandbox and the
declarative `Repo` describing how to build and start it. `registry.py` mounts
the `repo` defined here, the way a parent FastAPI app mounts a sub-app.
"""

from __future__ import annotations

from fastapi import FastAPI
from modal import Image, Sandbox

from modal_compose.layer import Layer, LayerContext, Repo, Runtime

app = FastAPI()


@app.get("/")
def read_root() -> dict[str, str]:
    return {"hello": "modal-compose"}


layer = Layer(name="api", runtime=Runtime(ports=[8000]))


@layer.build
def install(image: Image, ctx: LayerContext) -> Image:
    return image.pip_install("fastapi", "uvicorn", "pydantic", "modal").add_local_python_source(
        "devbox", "modal_compose"
    )


@layer.on_start
def serve(sandbox: Sandbox, ctx: LayerContext) -> None:
    sandbox.exec("uvicorn", "devbox.api:app", "--host", "0.0.0.0", "--port", "8000")


repo = Repo(layers=[layer])

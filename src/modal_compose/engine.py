from __future__ import annotations

import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4

import anyio
from modal import App, Sandbox, Secret

from .devbox import DevBox

if TYPE_CHECKING:
    from modal import Image
    from modal.container_process import ContainerProcess

    from .registry import Registry


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


async def terminate_sandbox(box: DevBox, sandbox: Sandbox) -> None:
    """Run each of `box`'s layer `on_terminate` hooks, then terminate `sandbox`."""
    for layer in box.layers:
        await _maybe_await(layer.on_terminate(sandbox))
    await sandbox.terminate.aio()


@dataclass
class Run:
    """A live sandbox created by an `Engine`; `terminate()` tears it down."""

    run_id: str
    sandbox: Sandbox
    engine: "Engine"

    @property
    def sandbox_id(self) -> str:
        return self.sandbox.object_id

    async def tunnels(self) -> dict[int, str]:
        tunnels = await self.sandbox.tunnels.aio()
        return {port: tunnel.url for port, tunnel in tunnels.items()}

    async def exec(self, *command: str) -> "ContainerProcess[str]":
        return await self.sandbox.exec.aio(*command)

    async def terminate(self) -> None:
        await self.engine.terminate(self)


@dataclass
class Engine:
    """The single-sandbox lifecycle for one `DevBox`.

    `image()` folds the box's layers over the base image, `build()` builds and
    publishes it under `image_name` (the box's name unless a registry
    namespaces it), `create()` launches the sandbox (with sidecars, then each
    layer's `on_start` in declaration order), and `terminate()` runs each
    layer's `on_terminate` before killing the sandbox. `run()` wraps
    `create()`/`terminate()` as an async context manager.
    """

    box: DevBox
    app: App
    base_image: "Image"
    image_name: str | None = None
    secrets: tuple[Secret, ...] = ()

    @classmethod
    def from_registry(cls, registry: "Registry", name: str, app: App) -> "Engine":
        return cls(
            box=registry[name],
            app=app,
            base_image=registry.base_image,
            image_name=registry.image_name_for(name),
            secrets=registry.common_secrets,
        )

    def image(self) -> "Image":
        return self.box.image(self.base_image)

    async def build(self) -> "Image":
        built = await self.image().build.aio(app=self.app)
        await built.publish.aio(name=self.image_name or self.box.name)
        return built

    def _secrets(self) -> list[Secret]:
        secrets = [*self.secrets, *self.box.secrets]
        if self.box.env:
            env: dict[str, str | None] = dict(self.box.env)
            secrets.append(Secret.from_dict(env))
        return secrets

    async def create(self, image: "Image | None" = None) -> Run:
        run_id = str(uuid4())
        create = cast(
            "Callable[..., Awaitable[Sandbox]]", cast(Any, Sandbox).create.aio
        )
        sandbox = await create(
            app=self.app,
            image=self.image() if image is None else image,
            encrypted_ports=self.box.ports,
            secrets=self._secrets(),
            timeout=self.box.timeout,
            cpu=self.box.cpu,
            memory=self.box.memory,
            gpu=self.box.gpu,
            workdir=self.box.workdir,
            tags={"box": self.box.name, "run": run_id},
        )
        try:
            await self._create_sidecars(sandbox)
            for layer in self.box.layers:
                await _maybe_await(layer.on_start(sandbox))
        except BaseException:
            with anyio.CancelScope(shield=True):
                await sandbox.terminate.aio()
            raise
        return Run(run_id=run_id, sandbox=sandbox, engine=self)

    @asynccontextmanager
    async def run(self, image: "Image | None" = None) -> AsyncGenerator[Run]:
        run = await self.create(image)
        try:
            yield run
        finally:
            with anyio.CancelScope(shield=True):
                await self.terminate(run)

    async def _create_sidecars(self, sandbox: Sandbox) -> None:
        for spec in self.box.sidecars:
            built = await spec.image.build.aio(app=self.app)
            await sandbox._experimental_sidecars.create.aio(
                *spec.command,
                name=spec.name,
                image=built,
                env=spec.env,
                secrets=list(spec.secrets),
            )

    async def terminate(self, run: Run) -> None:
        await terminate_sandbox(self.box, run.sandbox)

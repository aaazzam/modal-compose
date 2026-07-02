from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import anyio
from modal import App, Sandbox, Secret

from .devbox import DevBox

if TYPE_CHECKING:
    from modal import Image

    from .registry import Registry


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


@dataclass
class Run:
    """A live sandbox created by an `Engine`."""

    run_id: str
    sandbox: Sandbox

    @property
    def sandbox_id(self) -> str:
        return self.sandbox.object_id

    async def tunnels(self) -> dict[int, str]:
        tunnels = await self.sandbox.tunnels.aio()
        return {port: tunnel.url for port, tunnel in tunnels.items()}

    async def exec(self, *command: str) -> Any:
        return await self.sandbox.exec.aio(*command)


@dataclass
class Engine:
    """The single-sandbox lifecycle for one `DevBox`.

    `image()` folds the box's layers over the base image, `build()` builds and
    publishes it under the box's name, `create()` launches the sandbox (with
    sidecars, then each layer's `on_start` in declaration order), and
    `terminate()` runs each layer's `on_terminate` before killing the sandbox.
    """

    box: DevBox
    app: App
    base_image: "Image"
    timeout: int = 3600
    secrets: tuple[Secret, ...] = ()

    @classmethod
    def from_registry(cls, registry: "Registry", name: str, app: App) -> "Engine":
        return cls(
            box=registry[name],
            app=app,
            base_image=registry.base_image,
            secrets=registry.common_secrets,
        )

    def image(self) -> "Image":
        return self.box.image(self.base_image)

    async def build(self) -> "Image":
        built = await self.image().build.aio(app=self.app)
        await built.publish.aio(name=self.box.name)
        return built

    def _secrets(self) -> list[Secret]:
        deduped: dict[int, Secret] = {}
        for secret in (*self.secrets, *self.box.secrets):
            deduped.setdefault(id(secret), secret)
        secrets = list(deduped.values())
        if self.box.env:
            env: dict[str, str | None] = dict(self.box.env)
            secrets.append(Secret.from_dict(env))
        return secrets

    async def create(self, image: "Image | None" = None) -> Run:
        run_id = str(uuid4())
        sandbox = await Sandbox.create.aio(
            app=self.app,
            image=self.image() if image is None else image,
            encrypted_ports=self.box.ports,
            secrets=self._secrets(),
            timeout=self.timeout,
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
        return Run(run_id=run_id, sandbox=sandbox)

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
        for layer in self.box.layers:
            await _maybe_await(layer.on_terminate(run.sandbox))
        await run.sandbox.terminate.aio()

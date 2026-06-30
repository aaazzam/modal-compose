from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable
from uuid import uuid4

import anyio
from modal import App, Sandbox, Secret

from .layer import LayerContext, Repo

if TYPE_CHECKING:
    from modal import Image


async def _maybe_await(result: Any) -> None:
    if inspect.isawaitable(result):
        await result


async def run_hooks(
    bindings: Iterable[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]],
    sandbox: "Sandbox",
) -> None:
    for hook, ctx in bindings:
        await _maybe_await(hook(sandbox, ctx))


@dataclass
class Run:
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
    repo: Repo
    app: App
    name: str
    base_image: "Image"
    timeout: int = 3600
    secrets: set[Secret] = field(default_factory=set)

    def image(self) -> "Image":
        return self.repo.get_image(self.base_image)

    async def build(self) -> "Image":
        built = await self.image().build.aio(app=self.app)
        await built.publish.aio(name=self.name)
        return built

    def _secrets(self) -> list[Any]:
        secrets = list(self.secrets | self.repo.secrets)
        if self.repo.env:
            secrets.append(Secret.from_dict(self.repo.env))
        return secrets

    async def create(self, image: "Image | None" = None) -> Run:
        run_id = str(uuid4())
        sandbox = await Sandbox.create.aio(
            app=self.app,
            image=self.image() if image is None else image,
            encrypted_ports=self.repo.ports,
            secrets=self._secrets(),
            timeout=self.timeout,
            workdir=self.repo.working_directory,
            tags={"box": self.name, "run": run_id},
        )
        try:
            await run_hooks(self.repo.start_bindings, sandbox)
        except BaseException:
            with anyio.CancelScope(shield=True):
                await sandbox.terminate.aio()
            raise
        return Run(run_id=run_id, sandbox=sandbox)

    async def terminate(self, run: Run) -> None:
        await run_hooks(self.repo.terminate_bindings, run.sandbox)
        await run.sandbox.terminate.aio()

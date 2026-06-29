from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterable
from uuid import uuid4

import anyio
from modal import App, Sandbox, Secret

from .layer import Repo

if TYPE_CHECKING:
    from modal import Image


async def run_hooks(hooks: Iterable[Callable[..., Any]], sandbox: "Sandbox") -> None:
    for hook in hooks:
        result = hook(sandbox)
        if inspect.isawaitable(result):
            await result


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

    def image(self) -> "Image":
        return self.repo.get_image(self.base_image)

    async def build(self) -> "Image":
        built = await self.image().build.aio(app=self.app)
        await built.publish.aio(name=self.name)
        return built

    def _secrets(self) -> list[Any]:
        secrets = list(self.repo.secrets)
        if self.repo.env:
            secrets.append(Secret.from_dict(self.repo.env))
        return secrets

    async def create(self) -> Run:
        run_id = str(uuid4())
        sandbox = await Sandbox.create.aio(
            app=self.app,
            image=self.image(),
            encrypted_ports=self.repo.ports,
            secrets=self._secrets(),
            timeout=self.timeout,
            tags={"box": self.name, "run": run_id},
        )
        try:
            await sandbox.wait_until_ready.aio()
            await run_hooks(self.repo.starts, sandbox)
        except BaseException:
            with anyio.CancelScope(shield=True):
                await sandbox.terminate.aio()
            raise
        return Run(run_id=run_id, sandbox=sandbox)

    async def terminate(self, run: Run) -> None:
        await run_hooks(self.repo.terminates, run.sandbox)
        await run.sandbox.terminate.aio()

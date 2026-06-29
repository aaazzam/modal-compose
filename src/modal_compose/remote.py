from __future__ import annotations

from typing import TYPE_CHECKING

from modal import Image, Sandbox
from pydantic import BaseModel

if TYPE_CHECKING:
    from .layer import LayerContext


class Remote(BaseModel):
    working_directory: str

    def provision(self, image: Image) -> Image:
        raise NotImplementedError

    async def sync(self, sandbox: Sandbox, ctx: "LayerContext") -> None:
        raise NotImplementedError


class GitHubRemote(Remote):
    repo: str
    ref: str = "main"

    def provision(self, image: Image) -> Image:
        url = f"https://github.com/{self.repo}.git"
        return image.run_commands(
            f"git clone --branch {self.ref} {url} {self.working_directory}"
        )

    async def sync(self, sandbox: Sandbox, ctx: "LayerContext") -> None:
        await sandbox.exec.aio("git", "-C", self.working_directory, "pull", "--ff-only")

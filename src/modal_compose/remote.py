from __future__ import annotations

from modal import Image, Sandbox
from pydantic import BaseModel


class Remote(BaseModel):
    working_directory: str

    def provision(self, image: Image) -> Image:
        raise NotImplementedError

    async def refresh(self, sandbox: Sandbox) -> None:
        raise NotImplementedError


class GitHubRemote(Remote):
    repo: str
    ref: str = "main"

    def provision(self, image: Image) -> Image:
        url = f"https://github.com/{self.repo}.git"
        return image.run_commands(
            f"git clone --branch {self.ref} {url} {self.working_directory}"
        )

    async def refresh(self, sandbox: Sandbox) -> None:
        await sandbox.exec.aio("git", "-C", self.working_directory, "pull", "--ff-only")

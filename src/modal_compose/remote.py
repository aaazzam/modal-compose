from __future__ import annotations

from typing import TYPE_CHECKING

from modal import Image, Sandbox, Secret
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from .layer import LayerContext


class SidecarSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    image: Image
    command: list[str]
    env: dict[str, str] = Field(default_factory=dict)
    secrets: set[Secret] = Field(default_factory=set)


class Remote(BaseModel):
    working_directory: str

    def provision(self, image: Image) -> Image:
        raise NotImplementedError

    async def sync(self, sandbox: Sandbox, ctx: "LayerContext") -> None:
        raise NotImplementedError

    def sidecar(self) -> SidecarSpec | None:
        return None


_GITHUB_VAULT_NAME = "github-credential-vault"
_GITHUB_VAULT_PORT = 8765
_GITHUB_APP_SECRET_NAME = "modal-compose-github-app"


class GitHubRemote(Remote):
    repo: str
    ref: str = "main"
    private: bool = False

    @property
    def _account_and_repo(self) -> tuple[str, str]:
        return self.repo.split("/", 1)

    def provision(self, image: Image) -> Image:
        url = f"https://github.com/{self.repo}.git"
        if not self.private:
            return image.run_commands(
                f"git clone --branch {self.ref} {url} {self.working_directory}"
            )
        return self._provision_private(image, url)

    def _provision_private(self, image: Image, url: str) -> Image:
        account, repo_name = self._account_and_repo
        mint = f"TOKEN=$(python3 -m modal_compose.github_app {account} {repo_name})"
        clone = (
            f"git clone --branch {self.ref} "
            f"https://x-access-token:${{TOKEN}}@github.com/{self.repo}.git "
            f"{self.working_directory}"
        )
        scrub = f"git -C {self.working_directory} remote set-url origin {url}"
        return (
            image.pip_install("pyjwt", "cryptography", "requests")
            .add_local_python_source("modal_compose", copy=True)
            .run_commands(
                " && ".join((mint, clone, scrub)),
                secrets=[Secret.from_name(_GITHUB_APP_SECRET_NAME)],
            )
        )

    async def sync(self, sandbox: Sandbox, ctx: "LayerContext") -> None:
        await sandbox.exec.aio(
            "git",
            "-C",
            self.working_directory,
            "config",
            "credential.helper",
            self._credential_helper(),
        )
        await sandbox.exec.aio("git", "-C", self.working_directory, "pull", "--ff-only")

    def sidecar(self) -> SidecarSpec | None:
        account, repo_name = self._account_and_repo
        image = (
            Image.debian_slim()
            .pip_install("fastapi", "uvicorn", "pyjwt", "cryptography", "requests")
            .add_local_python_source("modal_compose", copy=True)
        )
        return SidecarSpec(
            name=_GITHUB_VAULT_NAME,
            image=image,
            command=[
                "uvicorn",
                "modal_compose._github_vault:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(_GITHUB_VAULT_PORT),
            ],
            env={"GITHUB_APP_ACCOUNT": account, "GITHUB_APP_REPO": repo_name},
            secrets={Secret.from_name(_GITHUB_APP_SECRET_NAME)},
        )

    def _credential_helper(self) -> str:
        url = f"http://{_GITHUB_VAULT_NAME}:{_GITHUB_VAULT_PORT}/token"
        return (
            "!f() { "
            "echo username=x-access-token; "
            f"curl -fsS -X POST {url} | jq -r '\"password=\" + .token'; "
            "}; f"
        )

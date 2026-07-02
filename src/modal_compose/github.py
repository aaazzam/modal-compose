from __future__ import annotations

from shlex import quote

from modal import Image, Sandbox, Secret
from pydantic import model_validator

from .layer import Layer, SidecarSpec

_GITHUB_VAULT_NAME = "github-credential-vault"
_GITHUB_VAULT_PORT = 8765
_GITHUB_APP_SECRET_NAME = "modal-compose-github-app"


def normalize_repo(repo: str) -> str:
    """Normalize a GitHub repo reference (URL or slug) to `owner/name`."""
    text = repo.strip().removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if text.startswith(prefix):
            text = text.removeprefix(prefix)
            break
    owner, _, name = text.strip("/").partition("/")
    if not owner or not name or "/" in name:
        raise ValueError(f"expected a GitHub repo like 'owner/name', got {repo!r}")
    return f"{owner}/{name}"


def default_workdir(repo: str) -> str:
    """The default checkout path for a normalized `owner/name` repo."""
    return f"/workspace/{repo.split('/', 1)[1]}"


class GitHub(Layer):
    """A layer that clones a GitHub repo at build time and `git pull`s it on start.

    `repo` accepts an `owner/name` slug or a GitHub URL and is normalized to
    the slug. `workdir` defaults to `/workspace/<name>`. Private repos are
    cloned with a short-lived GitHub App installation token (minted during the
    build, scrubbed from the git config afterwards); at runtime a credential
    vault sidecar brokers fresh tokens to git via a credential helper.
    """

    repo: str
    ref: str = "main"
    private: bool = False

    @model_validator(mode="after")
    def _normalize(self) -> "GitHub":
        self.repo = normalize_repo(self.repo)
        if self.workdir is None:
            self.workdir = default_workdir(self.repo)
        return self

    @property
    def _checkout(self) -> str:
        return self.workdir or default_workdir(self.repo)

    def build(self, image: Image) -> Image:
        url = f"https://github.com/{self.repo}.git"
        if not self.private:
            return image.run_commands(
                f"git clone --branch {quote(self.ref)} {url} {quote(self._checkout)}"
            )
        return self._build_private(image, url)

    def _build_private(self, image: Image, url: str) -> Image:
        account, name = self.repo.split("/", 1)
        mint = f"TOKEN=$(python3 -m modal_compose.github_app {quote(account)} {quote(name)})"
        clone = (
            f"git clone --branch {quote(self.ref)} "
            f"https://x-access-token:${{TOKEN}}@github.com/{self.repo}.git "
            f"{quote(self._checkout)}"
        )
        scrub = f"git -C {quote(self._checkout)} remote set-url origin {url}"
        return (
            image.pip_install("pyjwt", "cryptography", "requests")
            .add_local_python_source("modal_compose", copy=True)
            .run_commands(
                " && ".join((mint, clone, scrub)),
                secrets=[Secret.from_name(_GITHUB_APP_SECRET_NAME)],
            )
        )

    async def on_start(self, sandbox: Sandbox) -> None:
        await sandbox.exec.aio(
            "git",
            "-C",
            self._checkout,
            "config",
            "credential.helper",
            self._credential_helper(),
        )
        await sandbox.exec.aio("git", "-C", self._checkout, "pull", "--ff-only")

    def sidecar(self) -> SidecarSpec | None:
        account, name = self.repo.split("/", 1)
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
            env={"GITHUB_APP_ACCOUNT": account, "GITHUB_APP_REPO": name},
            secrets=(Secret.from_name(_GITHUB_APP_SECRET_NAME),),
        )

    def _credential_helper(self) -> str:
        url = f"http://{_GITHUB_VAULT_NAME}:{_GITHUB_VAULT_PORT}/token"
        return (
            "!f() { "
            "echo username=x-access-token; "
            f"curl -fsS -X POST {url} | jq -r '\"password=\" + .token'; "
            "}; f"
        )

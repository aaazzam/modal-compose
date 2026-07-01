from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from modal_compose.layer import Layer, LayerContext
from modal_compose.remote import GitHubRemote

from .conftest import FakeImage, StubRemote

pytestmark = pytest.mark.unit


class FakeExec:
    def __init__(self, calls: list[tuple[str, ...]]) -> None:
        self.calls = calls

    async def aio(self, *args: str) -> None:
        self.calls.append(args)


class FakeSandbox:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.exec = FakeExec(self.calls)


class TestGitHubRemote:
    def test_provision_clones_into_working_directory(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHubRemote(repo="acme/web", working_directory="/workspace/web").provision(
            image
        )
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/acme/web.git /workspace/web",
                ),
            )
        ]

    def test_provision_respects_ref(self, fake_image: Callable[[], FakeImage]) -> None:
        image = fake_image()
        GitHubRemote(repo="acme/web", working_directory="/w", ref="dev").provision(
            image
        )
        assert image.calls == [
            (
                "run_commands",
                ("git clone --branch dev https://github.com/acme/web.git /w",),
            )
        ]

    def test_sync_pulls_in_working_directory(self) -> None:
        sandbox = FakeSandbox()
        ctx = LayerContext(
            name="web",
            working_directory="/workspace/web",
            source=StubRemote(working_directory="/workspace/web"),
        )
        asyncio.run(
            GitHubRemote(repo="acme/web", working_directory="/workspace/web").sync(
                sandbox, ctx
            )
        )
        assert sandbox.calls[-1] == ("git", "-C", "/workspace/web", "pull", "--ff-only")

    def test_sync_configures_the_vault_credential_helper_first(self) -> None:
        sandbox = FakeSandbox()
        ctx = LayerContext(
            name="web",
            working_directory="/workspace/web",
            source=StubRemote(working_directory="/workspace/web"),
        )
        asyncio.run(
            GitHubRemote(repo="acme/web", working_directory="/workspace/web").sync(
                sandbox, ctx
            )
        )
        config_call = sandbox.calls[0]
        assert config_call[:4] == ("git", "-C", "/workspace/web", "config")
        assert config_call[4] == "credential.helper"
        assert "github-credential-vault:8765/token" in config_call[5]

    def test_sidecar_targets_the_repo_owner_account(self) -> None:
        spec = GitHubRemote(repo="acme/web", working_directory="/w").sidecar()
        assert spec is not None
        assert spec.name == "github-credential-vault"
        assert spec.env == {"GITHUB_APP_ACCOUNT": "acme", "GITHUB_APP_REPO": "web"}
        assert any(s.name == "modal-compose-github-app" for s in spec.secrets)

    def test_default_remote_has_no_sidecar(self) -> None:
        assert StubRemote(working_directory="/w").sidecar() is None


class TestGitHubRemotePrivate:
    def test_provision_is_anonymous_by_default(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHubRemote(repo="acme/web", working_directory="/w").provision(image)
        assert [name for name, _ in image.calls] == ["run_commands"]
        assert image.last_secrets is None

    def test_provision_mints_and_scrubs_the_token_when_private(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHubRemote(repo="acme/web", working_directory="/w", private=True).provision(
            image
        )

        assert [name for name, _ in image.calls] == [
            "pip_install",
            "add_local_python_source",
            "run_commands",
        ]

        clone_cmd = image.calls[-1][1][0]
        assert "python3 -m modal_compose.github_app acme web" in clone_cmd
        assert "https://x-access-token:${TOKEN}@github.com/acme/web.git" in clone_cmd
        assert "remote set-url origin https://github.com/acme/web.git" in clone_cmd

        assert image.last_secrets is not None
        assert any(s.name == "modal-compose-github-app" for s in image.last_secrets)


class TestLayerSource:
    def test_attaching_a_source_clones_on_apply(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        source = GitHubRemote(repo="acme/web", working_directory="/workspace/web")
        web = Layer(name="web", source=source)

        image = fake_image()
        web.apply(image)
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/acme/web.git /workspace/web",
                ),
            )
        ]
        assert web.source is source

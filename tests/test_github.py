from __future__ import annotations

import asyncio
from typing import Callable

import pytest
from pydantic import ValidationError

from modal_compose import GitHub
from modal_compose.github import normalize_repo

from .conftest import FakeImage

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


class TestRepoField:
    def test_accepts_a_slug(self) -> None:
        assert GitHub(repo="acme/web").repo == "acme/web"

    def test_normalizes_a_url(self) -> None:
        assert GitHub(repo="https://github.com/acme/Web.git").repo == "acme/Web"

    def test_normalizes_an_ssh_remote(self) -> None:
        assert GitHub(repo="git@github.com:acme/web.git").repo == "acme/web"

    def test_rejects_a_bare_name(self) -> None:
        with pytest.raises(ValidationError, match="owner/name"):
            GitHub(repo="not-a-repo")

    def test_rejects_a_typoed_field(self) -> None:
        with pytest.raises(ValidationError, match="branch"):
            GitHub(repo="acme/web", branch="dev")

    def test_normalize_repo_rejects_extra_segments(self) -> None:
        with pytest.raises(ValueError, match="owner/name"):
            normalize_repo("a/b/c")


class TestWorkdir:
    def test_defaults_to_workspace_slash_name(self) -> None:
        assert GitHub(repo="acme/web").workdir == "/workspace/web"

    def test_explicit_workdir_wins(self) -> None:
        assert GitHub(repo="acme/web", workdir="/srv/web").workdir == "/srv/web"


class TestBuild:
    def test_clones_into_the_workdir(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHub(repo="acme/web").build(image)
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/acme/web.git /workspace/web",
                ),
            )
        ]

    def test_respects_ref(self, fake_image: Callable[[], FakeImage]) -> None:
        image = fake_image()
        GitHub(repo="acme/web", ref="dev", workdir="/w").build(image)
        assert image.calls == [
            (
                "run_commands",
                ("git clone --branch dev https://github.com/acme/web.git /w",),
            )
        ]

    def test_quotes_shell_metacharacters_in_the_ref(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHub(repo="acme/web", ref="release; rm -rf /", workdir="/w").build(image)
        command = image.calls[0][1][0]
        assert "'release; rm -rf /'" in command


class TestOnStart:
    def test_pulls_in_the_workdir(self) -> None:
        sandbox = FakeSandbox()
        asyncio.run(GitHub(repo="acme/web").on_start(sandbox))
        assert sandbox.calls[-1] == (
            "git",
            "-C",
            "/workspace/web",
            "pull",
            "--ff-only",
        )

    def test_configures_the_vault_credential_helper_first(self) -> None:
        sandbox = FakeSandbox()
        asyncio.run(GitHub(repo="acme/web").on_start(sandbox))
        config_call = sandbox.calls[0]
        assert config_call[:4] == ("git", "-C", "/workspace/web", "config")
        assert config_call[4] == "credential.helper"
        assert "github-credential-vault:8765/token" in config_call[5]


class TestSidecar:
    def test_targets_the_repo_owner_account(self) -> None:
        spec = GitHub(repo="acme/web").sidecar()
        assert spec is not None
        assert spec.name == "github-credential-vault"
        assert spec.env == {"GITHUB_APP_ACCOUNT": "acme", "GITHUB_APP_REPO": "web"}
        assert any(s.name == "modal-compose-github-app" for s in spec.secrets)


class TestPrivate:
    def test_build_is_anonymous_by_default(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHub(repo="acme/web").build(image)
        assert [name for name, _ in image.calls] == ["run_commands"]
        assert image.last_secrets is None

    def test_build_mints_and_scrubs_the_token_when_private(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHub(repo="acme/web", private=True).build(image)

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

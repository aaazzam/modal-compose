from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from modal_compose.layer import Layer
from modal_compose.remote import GitHubRemote

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


class TestGitHubRemote:
    def test_provision_clones_into_working_directory(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        GitHubRemote(repo="ramp/web", working_directory="/workspace/web").provision(image)
        assert image.calls == [
            ("run_commands", ("git clone --branch main https://github.com/ramp/web.git /workspace/web",))
        ]

    def test_provision_respects_ref(self, fake_image: Callable[[], FakeImage]) -> None:
        image = fake_image()
        GitHubRemote(repo="ramp/web", working_directory="/w", ref="dev").provision(image)
        assert image.calls == [
            ("run_commands", ("git clone --branch dev https://github.com/ramp/web.git /w",))
        ]

    def test_refresh_pulls_in_working_directory(self) -> None:
        sandbox = FakeSandbox()
        asyncio.run(
            GitHubRemote(repo="ramp/web", working_directory="/workspace/web").refresh(sandbox)
        )
        assert sandbox.calls == [("git", "-C", "/workspace/web", "pull", "--ff-only")]


class TestExplicitWiring:
    def test_user_attaches_provision_and_refresh_themselves(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        web = Layer(name="web")
        source = GitHubRemote(repo="ramp/web", working_directory="/workspace/web")

        web.build(source.provision)
        web.on_start(source.refresh)

        image = fake_image()
        web.apply(image)
        assert image.calls == [
            ("run_commands", ("git clone --branch main https://github.com/ramp/web.git /workspace/web",))
        ]
        assert web.runtime.starts == [source.refresh]

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
        GitHubRemote(repo="ramp/web", working_directory="/workspace/web").provision(
            image
        )
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/ramp/web.git /workspace/web",
                ),
            )
        ]

    def test_provision_respects_ref(self, fake_image: Callable[[], FakeImage]) -> None:
        image = fake_image()
        GitHubRemote(repo="ramp/web", working_directory="/w", ref="dev").provision(
            image
        )
        assert image.calls == [
            (
                "run_commands",
                ("git clone --branch dev https://github.com/ramp/web.git /w",),
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
            GitHubRemote(repo="ramp/web", working_directory="/workspace/web").sync(
                sandbox, ctx
            )
        )
        assert sandbox.calls == [("git", "-C", "/workspace/web", "pull", "--ff-only")]


class TestLayerSource:
    def test_attaching_a_source_clones_on_apply(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        source = GitHubRemote(repo="ramp/web", working_directory="/workspace/web")
        web = Layer(name="web", source=source)

        image = fake_image()
        web.apply(image)
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/ramp/web.git /workspace/web",
                ),
            )
        ]
        assert web.source is source

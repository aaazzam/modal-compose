from __future__ import annotations

import asyncio
from typing import Callable

import pytest
from modal import Image, Sandbox

from modal_compose import Layer

from .conftest import FakeImage

pytestmark = pytest.mark.unit


class TestLayerDefaults:
    def test_constructs_with_no_arguments(self) -> None:
        layer = Layer()
        assert layer.workdir is None
        assert layer.env == {}
        assert layer.ports == []
        assert layer.secrets == ()

    def test_build_is_a_no_op(self, fake_image: Callable[[], FakeImage]) -> None:
        image = fake_image()
        assert Layer().build(image) is image
        assert image.calls == []

    def test_hooks_are_no_ops(self) -> None:
        sandbox = object()
        assert Layer().on_start(sandbox) is None
        assert Layer().on_terminate(sandbox) is None

    def test_has_no_sidecar(self) -> None:
        assert Layer().sidecar() is None


class TestLayerSubclass:
    def test_overridden_build_transforms_the_image(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        class Node(Layer):
            def build(self, image: Image) -> Image:
                return image.apt_install("nodejs")

        image = fake_image()
        assert Node().build(image) is image
        assert image.calls == [("apt_install", ("nodejs",))]

    def test_build_can_read_declared_fields_from_self(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        class Checkout(Layer):
            workdir: str = "/workspace/web"

            def build(self, image: Image) -> Image:
                return image.run_commands(f"cd {self.workdir} && uv sync")

        image = fake_image()
        Checkout().build(image)
        assert image.calls == [("run_commands", ("cd /workspace/web && uv sync",))]

    def test_async_on_start_override_is_awaitable(self) -> None:
        seen: list[object] = []

        class Web(Layer):
            async def on_start(self, sandbox: Sandbox) -> None:
                seen.append(sandbox)

        sandbox = object()
        asyncio.run(Web().on_start(sandbox))
        assert seen == [sandbox]

    def test_fields_declared_with_defaults_stay_per_instance(self) -> None:
        class Postgres(Layer):
            ports: list[int] = [5432]

        first = Postgres()
        second = Postgres()
        first.ports.append(5433)
        assert second.ports == [5432]

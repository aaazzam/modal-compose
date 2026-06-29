from __future__ import annotations

from typing import Callable

import pytest

from modal import Secret

from modal_compose.layer import Layer, Repo
from modal_compose.registry import Registry

from .conftest import FakeImage

pytestmark = pytest.mark.unit


def _repo(name: str) -> Repo:
    return Repo(layers=[Layer(name=name)])


class TestCommonSecrets:
    def test_defaults_to_an_empty_set(self) -> None:
        registry = Registry(base_image=FakeImage())
        assert registry.common_secrets == set()

    def test_stores_the_common_secrets(self) -> None:
        secret = Secret.from_dict({"A": "1"})
        registry = Registry(base_image=FakeImage(), common_secrets={secret})
        assert registry.common_secrets == {secret}


class TestMount:
    def test_mount_registers_and_returns_the_repo(self) -> None:
        registry = Registry(base_image=FakeImage())
        repo = _repo("api")
        assert registry.mount("api", repo) is repo
        assert registry.names() == ("api",)
        assert registry["api"] is repo
        assert "api" in registry
        assert len(registry) == 1

    def test_mount_rejects_duplicate_names(self) -> None:
        registry = Registry(base_image=FakeImage())
        registry.mount("api", _repo("api"))
        with pytest.raises(ValueError, match="already mounted"):
            registry.mount("api", _repo("api"))

    def test_names_and_items_preserve_mount_order(self) -> None:
        registry = Registry(base_image=FakeImage())
        registry.mount("api", _repo("api"))
        registry.mount("worker", _repo("worker"))
        assert registry.names() == ("api", "worker")
        assert [name for name, _ in registry.items()] == ["api", "worker"]


class TestImageFor:
    def test_image_for_folds_layers_over_the_base(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        base = fake_image()
        registry = Registry(base_image=base)
        layer = Layer(name="api")
        layer.build(lambda image, ctx: image.pip_install("fastapi"))
        registry.mount("api", Repo(layers=[layer]))
        assert registry.image_for("api") is base
        assert base.calls == [("pip_install", ("fastapi",))]

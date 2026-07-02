from __future__ import annotations

from typing import Callable

import pytest

from modal import Image, Secret

from modal_compose import DevBox, Layer, Registry

from .conftest import FakeImage

pytestmark = pytest.mark.unit


def _box(name: str) -> DevBox:
    return DevBox(name, layers=[Layer(workdir=f"/{name}")])


class TestCommonSecrets:
    def test_defaults_to_an_empty_tuple(self) -> None:
        registry = Registry(base_image=FakeImage())
        assert registry.common_secrets == ()

    def test_stores_the_common_secrets_in_order(self) -> None:
        first = Secret.from_dict({"A": "1"})
        second = Secret.from_dict({"B": "2"})
        registry = Registry(base_image=FakeImage(), common_secrets=(first, second))
        assert registry.common_secrets == (first, second)


class TestName:
    def test_defaults_to_modal_compose(self) -> None:
        assert Registry(base_image=FakeImage()).name == "modal-compose"

    def test_accepts_a_custom_name(self) -> None:
        assert Registry("acme-dev", base_image=FakeImage()).name == "acme-dev"

    def test_rejects_an_empty_name(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            Registry("", base_image=FakeImage())

    def test_image_name_for_prefixes_with_the_registry_name(self) -> None:
        registry = Registry("acme-dev", base_image=FakeImage())
        registry.add(_box("api"))
        assert registry.image_name_for("api") == "acme-dev-api"

    def test_image_name_for_rejects_an_unknown_box(self) -> None:
        registry = Registry(base_image=FakeImage())
        with pytest.raises(KeyError, match="registered: none"):
            registry.image_name_for("api")


class TestAdd:
    def test_add_registers_under_the_boxes_own_name(self) -> None:
        registry = Registry(base_image=FakeImage())
        box = _box("api")
        assert registry.add(box) is box
        assert tuple(registry) == ("api",)
        assert registry["api"] is box
        assert "api" in registry
        assert len(registry) == 1

    def test_add_rejects_duplicate_names(self) -> None:
        registry = Registry(base_image=FakeImage())
        registry.add(_box("api"))
        with pytest.raises(ValueError, match="already registered"):
            registry.add(_box("api"))

    def test_iteration_and_items_preserve_registration_order(self) -> None:
        registry = Registry(base_image=FakeImage())
        registry.add(_box("api"))
        registry.add(_box("worker"))
        assert list(registry) == ["api", "worker"]
        assert [name for name, _ in registry.items()] == ["api", "worker"]

    def test_supports_the_full_mapping_protocol(self) -> None:
        registry = Registry(base_image=FakeImage())
        box = registry.add(_box("api"))
        assert registry.get("api") is box
        assert registry.get("missing") is None
        assert list(registry.keys()) == ["api"]
        assert list(registry.values()) == [box]

    def test_missing_name_lists_what_is_registered(self) -> None:
        registry = Registry(base_image=FakeImage())
        registry.add(_box("api"))
        with pytest.raises(KeyError, match="registered: api"):
            registry["worker"]


class TestImageFor:
    def test_image_for_folds_layers_over_the_base(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        class Api(Layer):
            def build(self, image: Image) -> Image:
                return image.pip_install("fastapi")

        base = fake_image()
        registry = Registry(base_image=base)
        registry.add(DevBox("api", layers=[Api()]))
        assert registry.image_for("api") is base
        assert base.calls == [("pip_install", ("fastapi",))]

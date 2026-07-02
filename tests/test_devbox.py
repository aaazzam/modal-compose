from __future__ import annotations

from typing import Callable

import pytest
from modal import Image, Secret

from modal_compose import DevBox, Layer, SidecarSpec

from .conftest import FakeImage

pytestmark = pytest.mark.unit


class TestConstruction:
    def test_requires_a_layer_or_hook(self) -> None:
        with pytest.raises(ValueError, match="at least one layer"):
            DevBox("empty")

    def test_carries_its_own_name(self) -> None:
        box = DevBox("api", layers=[Layer()])
        assert box.name == "api"


class TestImage:
    def test_folds_layers_over_the_base_in_declaration_order(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        class First(Layer):
            def build(self, image: Image) -> Image:
                return image.apt_install("first")

        class Second(Layer):
            def build(self, image: Image) -> Image:
                return image.run_commands("second")

        base = fake_image()
        box = DevBox("api", layers=[First(), Second()])
        assert box.image(base) is base
        assert base.calls == [
            ("apt_install", ("first",)),
            ("run_commands", ("second",)),
        ]

    def test_inline_build_runs_after_the_layers(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        class Clone(Layer):
            def build(self, image: Image) -> Image:
                return image.run_commands("clone")

        box = DevBox(
            "api",
            layers=[Clone()],
            build=lambda image: image.pip_install("fastapi"),
        )
        base = fake_image()
        box.image(base)
        assert base.calls == [
            ("run_commands", ("clone",)),
            ("pip_install", ("fastapi",)),
        ]


class TestWorkdir:
    def test_explicit_workdir_wins(self) -> None:
        box = DevBox("api", layers=[Layer(workdir="/derived")], workdir="/explicit")
        assert box.workdir == "/explicit"

    def test_derives_from_the_first_layer_that_declares_one(self) -> None:
        box = DevBox("api", layers=[Layer(), Layer(workdir="/a"), Layer(workdir="/b")])
        assert box.workdir == "/a"

    def test_none_when_no_layer_declares_one(self) -> None:
        assert DevBox("api", layers=[Layer()]).workdir is None


class TestRuntimeSurface:
    def test_env_merges_with_later_layers_winning(self) -> None:
        box = DevBox(
            "api",
            layers=[Layer(env={"K": "old", "A": "1"}), Layer(env={"K": "new", "B": "2"})],
        )
        assert box.env == {"K": "new", "A": "1", "B": "2"}

    def test_ports_concatenate_across_layers(self) -> None:
        box = DevBox("api", layers=[Layer(ports=[8000]), Layer(ports=[5173])])
        assert box.ports == [8000, 5173]

    def test_secrets_accumulate_in_order_and_dedupe_by_identity(self) -> None:
        s1 = Secret.from_dict({"A": "1"})
        s2 = Secret.from_dict({"B": "2"})
        box = DevBox("api", layers=[Layer(secrets=(s1, s2)), Layer(secrets=(s1,))])
        assert box.secrets == (s1, s2)

    def test_box_level_settings_become_a_trailing_layer(self) -> None:
        box = DevBox(
            "api",
            layers=[Layer(env={"K": "layer"})],
            env={"K": "box"},
            ports=[9000],
        )
        assert box.env == {"K": "box"}
        assert box.ports == [9000]


class TestHooks:
    def test_inline_hooks_run_against_the_sandbox(self) -> None:
        seen: list[tuple[str, object]] = []
        box = DevBox(
            "api",
            on_start=lambda sandbox: seen.append(("start", sandbox)),
            on_terminate=lambda sandbox: seen.append(("stop", sandbox)),
        )
        sandbox = object()
        for layer in box.layers:
            layer.on_start(sandbox)
            layer.on_terminate(sandbox)
        assert seen == [("start", sandbox), ("stop", sandbox)]


class TestSidecars:
    def test_skips_layers_without_one(self) -> None:
        assert DevBox("api", layers=[Layer()]).sidecars == []

    def test_collects_each_layer_with_one_in_order(self) -> None:
        def spec(name: str) -> SidecarSpec:
            return SidecarSpec.model_construct(
                name=name, image=FakeImage(), command=["run"], env={}, secrets=()
            )

        class WithSidecar(Layer):
            sidecar_name: str

            def sidecar(self) -> SidecarSpec | None:
                return spec(self.sidecar_name)

        box = DevBox(
            "api",
            layers=[WithSidecar(sidecar_name="a"), Layer(), WithSidecar(sidecar_name="c")],
        )
        assert [s.name for s in box.sidecars] == ["a", "c"]

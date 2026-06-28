from __future__ import annotations

from typing import Callable

import pytest
from modal import Secret
from pydantic import ValidationError

from modal_compose.layer import Layer, Repo, Runtime

from .conftest import FakeImage

pytestmark = pytest.mark.unit


class TestLayerBuild:
    def test_build_registers_and_returns_the_function(self) -> None:
        ui = Layer(name="ui")

        @ui.build
        def transform(image: FakeImage) -> FakeImage:
            return image

        assert ui.builds == [transform]

    def test_apply_runs_the_build_transform(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        ui = Layer(name="ui")

        @ui.build
        def _(image: FakeImage) -> FakeImage:
            return image.apt_install("nodejs")

        image = fake_image()
        assert ui.apply(image) is image
        assert image.calls == [("apt_install", ("nodejs",))]

    def test_layer_without_builds_is_identity(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        assert Layer(name="x").apply(image) is image
        assert image.calls == []


class TestLayerLifecycle:
    def test_on_start_and_on_terminate_register_on_runtime(self) -> None:
        x = Layer(name="x")

        @x.on_start
        def start(box: object) -> None: ...

        @x.on_terminate
        def terminate(box: object) -> None: ...

        assert x.runtime.starts == [start]
        assert x.runtime.terminates == [terminate]


class TestRepoImage:
    def test_get_image_folds_layers_seeded_by_base(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        base = fake_image()

        first = Layer(name="first")
        first.build(lambda image: image.apt_install("first"))
        second = Layer(name="second")
        second.build(lambda image: image.run_commands("second"))

        repo = Repo(layers=[first, second])

        assert repo.get_image(base) is base
        assert base.calls == [("apt_install", ("first",)), ("run_commands", ("second",))]

    def test_empty_layers_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Repo(layers=[])


class TestRepoRuntime:
    def test_env_merges_with_later_layers_winning(self) -> None:
        a = Layer(name="a", runtime=Runtime(env={"K": "old", "A": "1"}))
        b = Layer(name="b", runtime=Runtime(env={"K": "new", "B": "2"}))
        assert Repo(layers=[a, b]).env == {"K": "new", "A": "1", "B": "2"}

    def test_secrets_union_across_layers(self) -> None:
        s1 = Secret.from_dict({"A": "1"})
        s2 = Secret.from_dict({"B": "2"})
        a = Layer(name="a", runtime=Runtime(secrets={s1}))
        b = Layer(name="b", runtime=Runtime(secrets={s2}))
        assert Repo(layers=[a, b]).secrets == {s1, s2}

    def test_ports_concatenate_across_layers(self) -> None:
        a = Layer(name="a", runtime=Runtime(ports=[8000]))
        b = Layer(name="b", runtime=Runtime(ports=[5173]))
        assert Repo(layers=[a, b]).ports == [8000, 5173]

    def test_starts_collect_in_layer_order(self) -> None:
        a = Layer(name="a")
        b = Layer(name="b")

        @a.on_start
        def start_a(box: object) -> None: ...

        @b.on_start
        def start_b(box: object) -> None: ...

        assert Repo(layers=[a, b]).starts == [start_a, start_b]

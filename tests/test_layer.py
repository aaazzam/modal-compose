from __future__ import annotations

from typing import Callable

import pytest
from modal import Secret
from pydantic import ValidationError

from modal_compose.layer import Layer, LayerContext, Repo, Runtime
from modal_compose.remote import GitHubRemote

from .conftest import FakeImage, StubRemote

pytestmark = pytest.mark.unit


def _stub(name: str, working_directory: str = "/w", **kwargs: object) -> Layer:
    return Layer(
        name=name, source=StubRemote(working_directory=working_directory), **kwargs
    )


class TestLayerBuild:
    def test_build_registers_and_returns_the_function(self) -> None:
        ui = _stub("ui")

        @ui.build
        def transform(image: FakeImage, ctx: LayerContext) -> FakeImage:
            return image

        assert ui.builds == [transform]

    def test_apply_runs_the_build_transform(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        ui = _stub("ui")

        @ui.build
        def _(image: FakeImage, ctx: LayerContext) -> FakeImage:
            return image.apt_install("nodejs")

        image = fake_image()
        assert ui.apply(image) is image
        assert image.calls == [("apt_install", ("nodejs",))]

    def test_layer_without_builds_just_provisions_the_source(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        image = fake_image()
        assert _stub("x").apply(image) is image
        assert image.calls == []


class TestLayerSource:
    def test_apply_provisions_the_source_before_builds(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        web = Layer(
            name="web",
            source=GitHubRemote(repo="acme/web", working_directory="/workspace/web"),
        )
        web.build(lambda image, ctx: image.pip_install("uv"))

        image = fake_image()
        web.apply(image)
        assert image.calls == [
            (
                "run_commands",
                (
                    "git clone --branch main https://github.com/acme/web.git /workspace/web",
                ),
            ),
            ("pip_install", ("uv",)),
        ]

    def test_build_can_read_the_working_directory_from_context(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        web = Layer(
            name="web",
            source=GitHubRemote(repo="acme/web", working_directory="/workspace/web"),
        )

        @web.build
        def install(image: FakeImage, ctx: LayerContext) -> FakeImage:
            return image.run_commands(f"cd {ctx.working_directory} && uv sync")

        image = fake_image()
        web.apply(image)
        assert image.calls[-1] == ("run_commands", ("cd /workspace/web && uv sync",))

    def test_working_directory_delegates_to_the_source(self) -> None:
        web = Layer(
            name="web",
            source=GitHubRemote(repo="acme/web", working_directory="/workspace/web"),
        )
        assert web.working_directory == "/workspace/web"
        assert web.context.working_directory == "/workspace/web"
        assert web.context.source is web.source


class TestLayerLifecycle:
    def test_on_start_and_on_terminate_register_on_runtime(self) -> None:
        x = _stub("x")

        @x.on_start
        def start(box: object, ctx: LayerContext) -> None: ...

        @x.on_terminate
        def terminate(box: object, ctx: LayerContext) -> None: ...

        assert x.runtime.starts == [start]
        assert x.runtime.terminates == [terminate]


class TestRepoImage:
    def test_get_image_folds_layers_seeded_by_base(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        base = fake_image()

        first = _stub("first")
        first.build(lambda image, ctx: image.apt_install("first"))
        second = _stub("second")
        second.build(lambda image, ctx: image.run_commands("second"))

        repo = Repo(layers=[first, second])

        assert repo.get_image(base) is base
        assert base.calls == [
            ("apt_install", ("first",)),
            ("run_commands", ("second",)),
        ]

    def test_empty_layers_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Repo(layers=[])

    def test_a_layer_requires_a_source(self) -> None:
        with pytest.raises(ValidationError):
            Layer(name="x")


class TestRepoSources:
    def test_sources_collect_every_layer_in_order(self) -> None:
        web = Layer(
            name="web", source=GitHubRemote(repo="acme/web", working_directory="/w")
        )
        api = Layer(
            name="api", source=GitHubRemote(repo="acme/api", working_directory="/a")
        )
        assert [s.working_directory for s in Repo(layers=[web, api]).sources] == [
            "/w",
            "/a",
        ]

    def test_working_directory_is_the_first_layers(self) -> None:
        first = _stub("first", working_directory="/first")
        second = _stub("second", working_directory="/second")
        assert Repo(layers=[first, second]).working_directory == "/first"


class TestRepoRuntime:
    def test_env_merges_with_later_layers_winning(self) -> None:
        a = _stub("a", runtime=Runtime(env={"K": "old", "A": "1"}))
        b = _stub("b", runtime=Runtime(env={"K": "new", "B": "2"}))
        assert Repo(layers=[a, b]).env == {"K": "new", "A": "1", "B": "2"}

    def test_secrets_union_across_layers(self) -> None:
        s1 = Secret.from_dict({"A": "1"})
        s2 = Secret.from_dict({"B": "2"})
        a = _stub("a", runtime=Runtime(secrets={s1}))
        b = _stub("b", runtime=Runtime(secrets={s2}))
        assert Repo(layers=[a, b]).secrets == {s1, s2}

    def test_ports_concatenate_across_layers(self) -> None:
        a = _stub("a", runtime=Runtime(ports=[8000]))
        b = _stub("b", runtime=Runtime(ports=[5173]))
        assert Repo(layers=[a, b]).ports == [8000, 5173]

    def test_start_bindings_lead_with_source_sync_then_user_hooks(self) -> None:
        a = Layer(name="a", source=GitHubRemote(repo="r/a", working_directory="/a"))
        b = Layer(name="b", source=GitHubRemote(repo="r/b", working_directory="/b"))

        @a.on_start
        def start_a(box: object, ctx: LayerContext) -> None: ...

        @b.on_start
        def start_b(box: object, ctx: LayerContext) -> None: ...

        bindings = Repo(layers=[a, b]).start_bindings
        assert [hook for hook, _ in bindings] == [
            a.source.sync,
            start_a,
            b.source.sync,
            start_b,
        ]
        assert [ctx.working_directory for _, ctx in bindings] == [
            "/a",
            "/a",
            "/b",
            "/b",
        ]


class TestRepoSidecars:
    def test_sidecars_skips_sources_without_one(self) -> None:
        a = _stub("a")
        assert Repo(layers=[a]).sidecars == []

    def test_sidecars_collects_each_layer_with_one(self) -> None:
        a = Layer(name="a", source=GitHubRemote(repo="acme/a", working_directory="/a"))
        b = _stub("b")
        c = Layer(name="c", source=GitHubRemote(repo="acme/c", working_directory="/c"))

        sidecars = Repo(layers=[a, b, c]).sidecars
        assert [s.env["GITHUB_APP_ACCOUNT"] for s in sidecars] == ["acme", "acme"]

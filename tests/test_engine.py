from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from modal import Secret

from modal_compose import engine
from modal_compose.engine import Engine, run_hooks
from modal_compose.layer import Layer, LayerContext, Repo, Runtime
from modal_compose.remote import Remote

from .conftest import FakeImage

CTX = LayerContext(name="t")

pytestmark = pytest.mark.unit


class _Aio:
    def __init__(self, fn: Callable[..., object]) -> None:
        self._fn = fn

    async def aio(self, *args: object, **kwargs: object) -> object:
        return self._fn(*args, **kwargs)


class FakeSandbox:
    def __init__(self) -> None:
        self.object_id = "sb-123"
        self.ready = False
        self.terminated = False
        self.wait_until_ready = _Aio(self._wait)
        self.terminate = _Aio(self._terminate)

    def _wait(self) -> None:
        self.ready = True

    def _terminate(self) -> None:
        self.terminated = True


class FakeSandboxFactory:
    def __init__(self, sandbox: FakeSandbox) -> None:
        self.sandbox = sandbox
        self.created_kwargs: dict[str, object] = {}
        self.create = _Aio(self._create)

    def _create(self, **kwargs: object) -> FakeSandbox:
        self.created_kwargs = kwargs
        return self.sandbox


class TestRunHooks:
    def test_runs_sync_and_async_hooks_in_order(self) -> None:
        calls: list[tuple[str, object]] = []

        def sync_hook(box: object, ctx: LayerContext) -> None:
            calls.append(("sync", box))

        async def async_hook(box: object, ctx: LayerContext) -> None:
            calls.append(("async", box))

        sandbox = object()
        asyncio.run(run_hooks([(sync_hook, CTX), (async_hook, CTX)], sandbox))

        assert calls == [("sync", sandbox), ("async", sandbox)]

    def test_passes_the_layer_context_to_each_hook(self) -> None:
        seen: list[LayerContext] = []

        def hook(box: object, ctx: LayerContext) -> None:
            seen.append(ctx)

        ctx = LayerContext(name="web", working_directory="/workspace/web")
        asyncio.run(run_hooks([(hook, ctx)], object()))
        assert seen == [ctx]

    def test_no_hooks_is_a_noop(self) -> None:
        asyncio.run(run_hooks([], object()))

    def test_awaits_async_hook_side_effects(self) -> None:
        done: list[bool] = []

        async def hook(box: object, ctx: LayerContext) -> None:
            await asyncio.sleep(0)
            done.append(True)

        asyncio.run(run_hooks([(hook, CTX)], object()))
        assert done == [True]


class TestCreate:
    def test_runs_start_hooks_after_create(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        factory = FakeSandboxFactory(sandbox)
        monkeypatch.setattr(engine, "Sandbox", factory)

        seen: list[object] = []
        web = Layer(name="web", runtime=Runtime(ports=[8000]))

        @web.on_start
        def _(box: object, ctx: LayerContext) -> None:
            seen.append(box)

        eng = Engine(
            repo=Repo(layers=[web]),
            app=object(),
            name="web",
            base_image=fake_image(),
            timeout=120,
        )
        run = asyncio.run(eng.create())

        assert seen == [sandbox]
        assert run.sandbox is sandbox
        assert factory.created_kwargs["timeout"] == 120
        assert factory.created_kwargs["encrypted_ports"] == [8000]
        assert factory.created_kwargs["tags"]["box"] == "web"

    def test_source_sync_runs_before_start_hooks_and_sets_workdir(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        factory = FakeSandboxFactory(sandbox)
        monkeypatch.setattr(engine, "Sandbox", factory)

        events: list[str] = []

        class RecordingRemote(Remote):
            def provision(self, image: object) -> object:
                return image

            async def sync(self, box: object, ctx: LayerContext) -> None:
                events.append("sync")

        web = Layer(name="web", source=RecordingRemote(working_directory="/workspace/web"))

        @web.on_start
        def _(box: object, ctx: LayerContext) -> None:
            events.append("start")

        eng = Engine(
            repo=Repo(layers=[web]), app=object(), name="web", base_image=fake_image()
        )
        asyncio.run(eng.create())

        assert events == ["sync", "start"]
        assert factory.created_kwargs["workdir"] == "/workspace/web"

    def test_terminates_the_sandbox_when_a_start_hook_fails(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        web = Layer(name="web")

        @web.on_start
        def _(box: object, ctx: LayerContext) -> None:
            raise RuntimeError("boom")

        eng = Engine(
            repo=Repo(layers=[web]), app=object(), name="web", base_image=fake_image()
        )
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(eng.create())

        assert sandbox.terminated is True


class TestSecrets:
    def test_unions_common_secrets_with_repo_secrets(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        common = Secret.from_dict({"COMMON": "1"})
        repo_secret = Secret.from_dict({"REPO": "2"})
        web = Layer(name="web", runtime=Runtime(secrets={repo_secret}))

        eng = Engine(
            repo=Repo(layers=[web]),
            app=object(),
            name="web",
            base_image=fake_image(),
            secrets={common},
        )

        assert set(eng._secrets()) == {common, repo_secret}

    def test_does_not_double_count_shared_secret(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        shared = Secret.from_dict({"SHARED": "1"})
        web = Layer(name="web", runtime=Runtime(secrets={shared}))

        eng = Engine(
            repo=Repo(layers=[web]),
            app=object(),
            name="web",
            base_image=fake_image(),
            secrets={shared},
        )

        secrets = eng._secrets()
        assert secrets == [shared]

    def test_create_passes_common_and_repo_secrets(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        factory = FakeSandboxFactory(sandbox)
        monkeypatch.setattr(engine, "Sandbox", factory)

        common = Secret.from_dict({"COMMON": "1"})
        repo_secret = Secret.from_dict({"REPO": "2"})
        web = Layer(name="web", runtime=Runtime(secrets={repo_secret}))

        eng = Engine(
            repo=Repo(layers=[web]),
            app=object(),
            name="web",
            base_image=fake_image(),
            secrets={common},
        )
        asyncio.run(eng.create())

        assert set(factory.created_kwargs["secrets"]) == {common, repo_secret}

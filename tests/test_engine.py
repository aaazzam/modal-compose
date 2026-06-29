from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from modal_compose import engine
from modal_compose.engine import Engine, run_hooks
from modal_compose.layer import Layer, Repo, Runtime

from .conftest import FakeImage

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

        def sync_hook(box: object) -> None:
            calls.append(("sync", box))

        async def async_hook(box: object) -> None:
            calls.append(("async", box))

        sandbox = object()
        asyncio.run(run_hooks([sync_hook, async_hook], sandbox))

        assert calls == [("sync", sandbox), ("async", sandbox)]

    def test_no_hooks_is_a_noop(self) -> None:
        asyncio.run(run_hooks([], object()))

    def test_awaits_async_hook_side_effects(self) -> None:
        done: list[bool] = []

        async def hook(box: object) -> None:
            await asyncio.sleep(0)
            done.append(True)

        asyncio.run(run_hooks([hook], object()))
        assert done == [True]


class TestCreate:
    def test_waits_for_readiness_then_runs_start_hooks(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        factory = FakeSandboxFactory(sandbox)
        monkeypatch.setattr(engine, "Sandbox", factory)

        seen: list[object] = []
        web = Layer(name="web", runtime=Runtime(ports=[8000]))

        @web.on_start
        def _(box: object) -> None:
            assert sandbox.ready is True
            seen.append(box)

        eng = Engine(
            repo=Repo(layers=[web]),
            app=object(),
            name="web",
            base_image=fake_image(),
            timeout=120,
        )
        run = asyncio.run(eng.create())

        assert sandbox.ready is True
        assert seen == [sandbox]
        assert run.sandbox is sandbox
        assert factory.created_kwargs["timeout"] == 120
        assert factory.created_kwargs["encrypted_ports"] == [8000]
        assert factory.created_kwargs["tags"]["box"] == "web"

    def test_terminates_the_sandbox_when_a_start_hook_fails(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        web = Layer(name="web")

        @web.on_start
        def _(box: object) -> None:
            raise RuntimeError("boom")

        eng = Engine(
            repo=Repo(layers=[web]), app=object(), name="web", base_image=fake_image()
        )
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(eng.create())

        assert sandbox.terminated is True

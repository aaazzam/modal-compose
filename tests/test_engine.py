from __future__ import annotations

import asyncio
from typing import Callable

import pytest

from modal import Sandbox, Secret

from modal_compose import DevBox, Layer, Registry, SidecarSpec
from modal_compose import engine
from modal_compose.engine import Engine

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
        self.terminated = False
        self.terminate = _Aio(self._terminate)

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


def _engine(box: DevBox, base_image: FakeImage, **kwargs: object) -> Engine:
    return Engine(box=box, app=object(), base_image=base_image, **kwargs)


class TestCreate:
    def test_runs_start_hooks_after_create(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        factory = FakeSandboxFactory(sandbox)
        monkeypatch.setattr(engine, "Sandbox", factory)

        seen: list[object] = []

        class Web(Layer):
            def on_start(self, sandbox: Sandbox) -> None:
                seen.append(sandbox)

        box = DevBox(
            "web",
            layers=[Web(workdir="/workspace/web", ports=[8000])],
            timeout=120,
            cpu=2.0,
            memory=4096,
            gpu="A10G",
        )
        run = asyncio.run(_engine(box, fake_image()).create())

        assert seen == [sandbox]
        assert run.sandbox is sandbox
        assert run.sandbox_id == "sb-123"
        assert factory.created_kwargs["timeout"] == 120
        assert factory.created_kwargs["cpu"] == 2.0
        assert factory.created_kwargs["memory"] == 4096
        assert factory.created_kwargs["gpu"] == "A10G"
        assert factory.created_kwargs["encrypted_ports"] == [8000]
        assert factory.created_kwargs["workdir"] == "/workspace/web"
        assert factory.created_kwargs["tags"]["box"] == "web"

    def test_runs_sync_and_async_hooks_in_declaration_order(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []

        class SyncFirst(Layer):
            def on_start(self, sandbox: Sandbox) -> None:
                events.append("sync")

        class AsyncSecond(Layer):
            async def on_start(self, sandbox: Sandbox) -> None:
                await asyncio.sleep(0)
                events.append("async")

        box = DevBox("web", layers=[SyncFirst(), AsyncSecond()])
        asyncio.run(_engine(box, fake_image()).create())

        assert events == ["sync", "async"]

    def test_inline_start_hook_runs_after_layer_hooks(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []

        class Web(Layer):
            def on_start(self, sandbox: Sandbox) -> None:
                events.append("layer")

        box = DevBox(
            "web", layers=[Web()], on_start=lambda sandbox: events.append("inline")
        )
        asyncio.run(_engine(box, fake_image()).create())

        assert events == ["layer", "inline"]

    def test_terminates_the_sandbox_when_a_start_hook_fails(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        class Boom(Layer):
            def on_start(self, sandbox: Sandbox) -> None:
                raise RuntimeError("boom")

        box = DevBox("web", layers=[Boom()])
        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(_engine(box, fake_image()).create())

        assert sandbox.terminated is True


class TestTerminate:
    def test_runs_terminate_hooks_then_kills_the_sandbox(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []

        class Web(Layer):
            def on_terminate(self, sandbox: Sandbox) -> None:
                events.append("terminate")

        eng = _engine(DevBox("web", layers=[Web()]), fake_image())
        run = asyncio.run(eng.create())
        asyncio.run(eng.terminate(run))

        assert events == ["terminate"]
        assert sandbox.terminated is True

    def test_run_terminates_itself(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []

        class Web(Layer):
            def on_terminate(self, sandbox: Sandbox) -> None:
                events.append("terminate")

        run = asyncio.run(_engine(DevBox("web", layers=[Web()]), fake_image()).create())
        asyncio.run(run.terminate())

        assert events == ["terminate"]
        assert sandbox.terminated is True

    def test_run_context_manager_creates_and_terminates(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []

        class Web(Layer):
            def on_start(self, sandbox: Sandbox) -> None:
                events.append("start")

            def on_terminate(self, sandbox: Sandbox) -> None:
                events.append("terminate")

        async def use() -> None:
            async with _engine(DevBox("web", layers=[Web()]), fake_image()).run() as run:
                events.append(f"inside:{run.sandbox_id}")

        asyncio.run(use())

        assert events == ["start", "inside:sb-123", "terminate"]
        assert sandbox.terminated is True

    def test_run_context_manager_terminates_on_error(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        async def use() -> None:
            async with _engine(DevBox("web", layers=[Layer()]), fake_image()).run():
                raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            asyncio.run(use())

        assert sandbox.terminated is True


class TestSecrets:
    def test_orders_common_secrets_before_box_secrets(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        common = Secret.from_dict({"COMMON": "1"})
        box_secret = Secret.from_dict({"BOX": "2"})
        box = DevBox("web", layers=[Layer(secrets=(box_secret,))])

        eng = _engine(box, fake_image(), secrets=(common,))
        assert eng._secrets() == [common, box_secret]

    def test_accumulates_a_repeated_secret_in_order(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        shared = Secret.from_dict({"SHARED": "1"})
        box = DevBox("web", layers=[Layer(secrets=(shared,))])

        eng = _engine(box, fake_image(), secrets=(shared,))
        assert eng._secrets() == [shared, shared]

    def test_env_is_appended_as_a_final_secret(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        declared = Secret.from_dict({"A": "1"})
        box = DevBox("web", layers=[Layer(env={"K": "V"}, secrets=(declared,))])

        secrets = _engine(box, fake_image())._secrets()
        assert secrets[0] is declared
        assert len(secrets) == 2

    def test_no_env_means_no_extra_secret(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        box = DevBox("web", layers=[Layer()])
        assert _engine(box, fake_image())._secrets() == []


class TestFromRegistry:
    def test_wires_the_box_base_image_and_common_secrets(
        self, fake_image: Callable[[], FakeImage]
    ) -> None:
        common = Secret.from_dict({"COMMON": "1"})
        base = fake_image()
        registry = Registry(base_image=base, common_secrets=(common,))
        box = registry.add(DevBox("web", layers=[Layer()]))

        app = object()
        eng = Engine.from_registry(registry, "web", app)

        assert eng.box is box
        assert eng.app is app
        assert eng.base_image is base
        assert eng.secrets == (common,)
        assert eng.image_name == "modal-compose-web"


class FakeSidecarImage:
    def __init__(self, events: list[str], built: object = "built-image") -> None:
        self._events = events
        self._built = built
        self.build = _Aio(self._build)

    def _build(self, **kwargs: object) -> object:
        self._events.append("build")
        return self._built


class FakeSidecarManager:
    def __init__(self, events: list[str]) -> None:
        self._events = events
        self.created: list[dict[str, object]] = []
        self.create = _Aio(self._create)

    def _create(self, *args: object, **kwargs: object) -> object:
        self._events.append("create")
        self.created.append({"args": args, **kwargs})
        return object()


class TestSidecars:
    def test_create_never_touches_sidecars_when_no_layer_has_one(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        box = DevBox("web", layers=[Layer()])
        asyncio.run(_engine(box, fake_image()).create())

        assert not hasattr(sandbox, "_experimental_sidecars")

    def test_create_builds_and_creates_sidecars_before_start_hooks(
        self, monkeypatch: pytest.MonkeyPatch, fake_image: Callable[[], FakeImage]
    ) -> None:
        sandbox = FakeSandbox()
        monkeypatch.setattr(engine, "Sandbox", FakeSandboxFactory(sandbox))

        events: list[str] = []
        sandbox._experimental_sidecars = FakeSidecarManager(events)

        spec = SidecarSpec.model_construct(
            name="gh-vault",
            image=FakeSidecarImage(events),
            command=["uvicorn", "app:app"],
            env={"GITHUB_APP_ACCOUNT": "acme"},
            secrets=(),
        )

        class Vaulted(Layer):
            def sidecar(self) -> SidecarSpec | None:
                return spec

            def on_start(self, sandbox: Sandbox) -> None:
                events.append("start")

        box = DevBox("web", layers=[Vaulted()])
        asyncio.run(_engine(box, fake_image()).create())

        assert events == ["build", "create", "start"]
        [created] = sandbox._experimental_sidecars.created
        assert created == {
            "args": ("uvicorn", "app:app"),
            "name": "gh-vault",
            "image": "built-image",
            "env": {"GITHUB_APP_ACCOUNT": "acme"},
            "secrets": [],
        }

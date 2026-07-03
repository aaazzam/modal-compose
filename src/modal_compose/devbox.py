from __future__ import annotations

import re
from collections.abc import Awaitable, Mapping, Sequence
from functools import reduce
from typing import Callable

from modal import Image, Sandbox, Secret

from .layer import Layer, SidecarSpec

BuildFn = Callable[[Image], Image]
HookFn = Callable[[Sandbox], Awaitable[None] | None]

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class _InlineLayer(Layer):
    build_fn: BuildFn | None = None
    on_start_fn: HookFn | None = None
    on_terminate_fn: HookFn | None = None

    def build(self, image: Image) -> Image:
        return self.build_fn(image) if self.build_fn else image

    def on_start(self, sandbox: Sandbox) -> Awaitable[None] | None:
        return self.on_start_fn(sandbox) if self.on_start_fn else None

    def on_terminate(self, sandbox: Sandbox) -> Awaitable[None] | None:
        return self.on_terminate_fn(sandbox) if self.on_terminate_fn else None


class DevBox:
    """A named dev-box: an ordered stack of `Layer`s plus box-level settings.

    The image is built by folding each layer's `build` over the base image in
    declaration order; `env` merges across layers with later layers winning;
    `ports` and `secrets` accumulate in declaration order. `workdir` is where
    the sandbox starts: pass it explicitly or it is derived from the last
    layer that declares one (a `GitHub` layer always does), mirroring how
    `env` merges.

    `timeout`, `cpu`, `memory`, and `gpu` size the sandbox: `timeout` is the
    sandbox lifetime in seconds, and the rest are passed straight through to
    `modal.Sandbox.create`.

    The `build`, `on_start`, and `on_terminate` keyword arguments, along with
    box-level `env` / `ports` / `secrets`, are sugar for one final inline
    layer, so a single-repo box needs no `Layer` subclass at all.
    """

    def __init__(
        self,
        name: str,
        *,
        layers: Sequence[Layer] = (),
        workdir: str | None = None,
        env: Mapping[str, str] | None = None,
        ports: Sequence[int] | None = None,
        secrets: Sequence[Secret] | None = None,
        build: BuildFn | None = None,
        on_start: HookFn | None = None,
        on_terminate: HookFn | None = None,
        timeout: int = 3600,
        cpu: float | None = None,
        memory: int | None = None,
        gpu: str | None = None,
    ) -> None:
        if not _NAME_PATTERN.match(name):
            raise ValueError(
                f"DevBox name {name!r} must be 1-64 characters of letters, digits, "
                "dots, dashes, or underscores, starting with a letter or digit"
            )
        if timeout < 1:
            raise ValueError(f"DevBox timeout must be positive, got {timeout}")
        self.name = name
        stack = list(layers)
        if env or ports or secrets or build or on_start or on_terminate:
            stack.append(
                _InlineLayer(
                    env=dict(env or {}),
                    ports=list(ports or []),
                    secrets=tuple(secrets or ()),
                    build_fn=build,
                    on_start_fn=on_start,
                    on_terminate_fn=on_terminate,
                )
            )
        if not stack:
            raise ValueError(
                f"DevBox {name!r} needs at least one layer, build step, or hook"
            )
        self.layers: list[Layer] = stack
        self.timeout = timeout
        self.cpu = cpu
        self.memory = memory
        self.gpu = gpu
        self._workdir = workdir

    def __repr__(self) -> str:
        return f"DevBox({self.name!r}, layers={self.layers!r})"

    @property
    def workdir(self) -> str | None:
        if self._workdir is not None:
            return self._workdir
        return next(
            (
                layer.workdir
                for layer in reversed(self.layers)
                if layer.workdir is not None
            ),
            None,
        )

    def image(self, base: Image) -> Image:
        return reduce(lambda image, layer: layer.build(image), self.layers, base)

    @property
    def env(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for layer in self.layers:
            merged |= layer.env
        return merged

    @property
    def ports(self) -> list[int]:
        return [port for layer in self.layers for port in layer.ports]

    @property
    def secrets(self) -> tuple[Secret, ...]:
        return tuple(secret for layer in self.layers for secret in layer.secrets)

    @property
    def sidecars(self) -> list[SidecarSpec]:
        return [spec for layer in self.layers if (spec := layer.sidecar()) is not None]

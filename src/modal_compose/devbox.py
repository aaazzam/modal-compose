from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import reduce
from typing import Any, Callable

from modal import Image, Sandbox, Secret

from .layer import Layer, SidecarSpec

BuildFn = Callable[[Image], Image]
HookFn = Callable[[Sandbox], Any]


class _InlineLayer(Layer):
    build_fn: BuildFn | None = None
    on_start_fn: HookFn | None = None
    on_terminate_fn: HookFn | None = None

    def build(self, image: Image) -> Image:
        return self.build_fn(image) if self.build_fn else image

    def on_start(self, sandbox: Sandbox) -> Any:
        return self.on_start_fn(sandbox) if self.on_start_fn else None

    def on_terminate(self, sandbox: Sandbox) -> Any:
        return self.on_terminate_fn(sandbox) if self.on_terminate_fn else None


class DevBox:
    """A named dev-box: an ordered stack of `Layer`s plus box-level settings.

    The image is built by folding each layer's `build` over the base image in
    declaration order; `env` merges across layers with later layers winning;
    `ports` and `secrets` accumulate in order. `workdir` is where the sandbox
    starts: pass it explicitly or it is derived from the first layer that
    declares one (a `GitHub` layer always does).

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
    ) -> None:
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
        self._workdir = workdir

    @property
    def workdir(self) -> str | None:
        if self._workdir is not None:
            return self._workdir
        return next(
            (layer.workdir for layer in self.layers if layer.workdir is not None), None
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
        deduped: dict[int, Secret] = {}
        for layer in self.layers:
            for secret in layer.secrets:
                deduped.setdefault(id(secret), secret)
        return tuple(deduped.values())

    @property
    def sidecars(self) -> list[SidecarSpec]:
        return [spec for layer in self.layers if (spec := layer.sidecar()) is not None]

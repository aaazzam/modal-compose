from __future__ import annotations

from functools import reduce
from typing import Any, Callable

from modal import Image, Sandbox, Secret
from pydantic import BaseModel, ConfigDict, Field

from .remote import Remote, SidecarSpec


class LayerContext(BaseModel):
    name: str
    working_directory: str | None = None
    source: Remote


class Runtime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    env: dict[str, str] = Field(default_factory=dict)
    secrets: set[Secret] = Field(default_factory=set)
    ports: list[int] = Field(default_factory=list)
    starts: list[Callable[[Sandbox, LayerContext], Any]] = Field(
        default_factory=list, max_length=1
    )
    terminates: list[Callable[[Sandbox, LayerContext], Any]] = Field(
        default_factory=list, max_length=1
    )


class Layer(BaseModel, arbitrary_types_allowed=True):
    name: str
    source: Remote
    builds: list[Callable[[Image, LayerContext], Image]] = Field(
        default_factory=list, max_length=1
    )
    runtime: Runtime = Field(default_factory=Runtime)

    @property
    def working_directory(self) -> str:
        return self.source.working_directory

    @property
    def context(self) -> LayerContext:
        return LayerContext(
            name=self.name,
            working_directory=self.working_directory,
            source=self.source,
        )

    def build(
        self, fn: Callable[[Image, LayerContext], Image]
    ) -> Callable[[Image, LayerContext], Image]:
        self.builds.append(fn)
        return fn

    def on_start(
        self, fn: Callable[[Sandbox, LayerContext], Any]
    ) -> Callable[[Sandbox, LayerContext], Any]:
        self.runtime.starts.append(fn)
        return fn

    def on_terminate(
        self, fn: Callable[[Sandbox, LayerContext], Any]
    ) -> Callable[[Sandbox, LayerContext], Any]:
        self.runtime.terminates.append(fn)
        return fn

    def apply(self, image: Image) -> Image:
        seeded = self.source.provision(image)
        ctx = self.context
        return reduce(
            lambda current, transform: transform(current, ctx), self.builds, seeded
        )

    @property
    def sidecar(self) -> SidecarSpec | None:
        return self.source.sidecar()

    @property
    def start_bindings(
        self,
    ) -> list[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]]:
        ctx = self.context
        bindings: list[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]] = [
            (self.source.sync, ctx)
        ]
        bindings.extend((hook, ctx) for hook in self.runtime.starts)
        return bindings

    @property
    def terminate_bindings(
        self,
    ) -> list[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]]:
        ctx = self.context
        return [(hook, ctx) for hook in self.runtime.terminates]


class Repo(BaseModel, arbitrary_types_allowed=True):
    layers: list[Layer] = Field(min_length=1)

    def get_image(self, base_image: "Image") -> "Image":
        return reduce(
            lambda image, layer: layer.apply(image),
            self.layers,
            base_image,
        )

    @property
    def sources(self) -> list[Remote]:
        return [layer.source for layer in self.layers]

    @property
    def working_directory(self) -> str:
        return self.layers[0].working_directory

    @property
    def env(self) -> dict[str, str]:
        return reduce(
            lambda a, b: a | b.runtime.env,
            self.layers,
            dict[str, str](),
        )

    @property
    def secrets(self) -> set["Secret"]:
        return reduce(
            lambda a, b: a | b.runtime.secrets,
            self.layers,
            set["Secret"](),
        )

    @property
    def ports(self) -> list[int]:
        return reduce(
            lambda a, b: a + b.runtime.ports,
            self.layers,
            list[int](),
        )

    @property
    def sidecars(self) -> list[SidecarSpec]:
        candidates = (layer.sidecar for layer in self.layers)
        return [spec for spec in candidates if spec is not None]

    @property
    def start_bindings(
        self,
    ) -> list[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]]:
        return [binding for layer in self.layers for binding in layer.start_bindings]

    @property
    def terminate_bindings(
        self,
    ) -> list[tuple[Callable[[Sandbox, LayerContext], Any], LayerContext]]:
        return [
            binding for layer in self.layers for binding in layer.terminate_bindings
        ]

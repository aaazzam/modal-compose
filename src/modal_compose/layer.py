from __future__ import annotations

from functools import reduce
from typing import Any, Callable

from modal import Image, Sandbox, Secret
from pydantic import BaseModel, ConfigDict, Field

from .remote import Remote


class LayerContext(BaseModel):
    name: str
    working_directory: str | None = None


ImageTransform = Callable[[Image, LayerContext], Image]
SandboxLifecycleHook = Callable[[Sandbox, LayerContext], Any]
LifecycleBinding = tuple[SandboxLifecycleHook, LayerContext]


class Runtime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    env: dict[str, str] = Field(default_factory=dict)
    secrets: set[Secret] = Field(default_factory=set)
    ports: list[int] = Field(default_factory=list)
    starts: list[SandboxLifecycleHook] = Field(default_factory=list, max_length=1)
    terminates: list[SandboxLifecycleHook] = Field(default_factory=list, max_length=1)


class Layer(BaseModel, arbitrary_types_allowed=True):
    name: str
    source: Remote | None = None
    builds: list[ImageTransform] = Field(default_factory=list, max_length=1)
    runtime: Runtime = Field(default_factory=Runtime)

    @property
    def working_directory(self) -> str | None:
        return None if self.source is None else self.source.working_directory

    @property
    def context(self) -> LayerContext:
        return LayerContext(name=self.name, working_directory=self.working_directory)

    def build(self, fn: ImageTransform) -> ImageTransform:
        self.builds.append(fn)
        return fn

    def on_start(self, fn: SandboxLifecycleHook) -> SandboxLifecycleHook:
        self.runtime.starts.append(fn)
        return fn

    def on_terminate(self, fn: SandboxLifecycleHook) -> SandboxLifecycleHook:
        self.runtime.terminates.append(fn)
        return fn

    def apply(self, image: "Image") -> "Image":
        seeded = image if self.source is None else self.source.provision(image)
        ctx = self.context
        return reduce(lambda current, transform: transform(current, ctx), self.builds, seeded)

    @property
    def start_bindings(self) -> list[LifecycleBinding]:
        ctx = self.context
        bindings: list[LifecycleBinding] = []
        if self.source is not None:
            bindings.append((self.source.sync, ctx))
        bindings.extend((hook, ctx) for hook in self.runtime.starts)
        return bindings

    @property
    def terminate_bindings(self) -> list[LifecycleBinding]:
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
        return [layer.source for layer in self.layers if layer.source is not None]

    @property
    def working_directory(self) -> str | None:
        for layer in self.layers:
            if layer.working_directory is not None:
                return layer.working_directory
        return None

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
    def start_bindings(self) -> list[LifecycleBinding]:
        return [binding for layer in self.layers for binding in layer.start_bindings]

    @property
    def terminate_bindings(self) -> list[LifecycleBinding]:
        return [binding for layer in self.layers for binding in layer.terminate_bindings]

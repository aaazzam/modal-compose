from __future__ import annotations

from functools import reduce
from typing import Any, Callable

from modal import Image, Sandbox, Secret
from pydantic import BaseModel, ConfigDict, Field

ImageTransform = Callable[[Image], Image]
SandboxLifecycleHook = Callable[[Sandbox], None]


class Runtime(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    env: dict[str, str] = Field(default_factory=dict)
    secrets: set[Secret] = Field(default_factory=set)
    ports: list[int] = Field(default_factory=list)
    starts: list[SandboxLifecycleHook] = Field(default_factory=list, max_length=1)
    terminates: list[SandboxLifecycleHook] = Field(default_factory=list, max_length=1)


class Layer(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    builds: list[ImageTransform] = Field(default_factory=list, max_length=1)
    runtime: Runtime = Field(default_factory=Runtime)

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
        return reduce(lambda current, transform: transform(current), self.builds, image)


class Repo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    layers: list[Layer] = Field(min_length=1)

    def get_image(self, base_image: "Image") -> "Image":
        return reduce(
            lambda image, layer: layer.apply(image),
            self.layers,
            base_image,
        )

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
    def starts(self) -> list[Callable[..., Any]]:
        return reduce(
            lambda a, b: a + b.runtime.starts,
            self.layers,
            list[SandboxLifecycleHook](),
        )

    @property
    def terminates(self) -> list[Callable[..., Any]]:
        return list(
            reduce(
                lambda a, b: a + b.runtime.terminates,
                self.layers,
                list[SandboxLifecycleHook](),
            )
        )

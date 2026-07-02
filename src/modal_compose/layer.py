from __future__ import annotations

from typing import Any

from modal import Image, Sandbox, Secret
from pydantic import BaseModel, ConfigDict


class SidecarSpec(BaseModel):
    """A companion container that runs alongside the sandbox on its private network."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    image: Image
    command: list[str]
    env: dict[str, str] = {}
    secrets: tuple[Secret, ...] = ()


class Layer(BaseModel):
    """One slice of a dev-box, spanning image build time and sandbox runtime.

    The fields declare the layer's runtime surface: `workdir` is where its code
    lives in the sandbox (if anywhere), and `env`, `ports`, and `secrets` are
    merged across the stack by `DevBox`. The four methods are the overridable
    moments of the lifecycle: `build` transforms the `modal.Image` during the
    phased, declaration-order image build; `on_start` and `on_terminate` run
    against the live sandbox (either may be sync or async); `sidecar` declares
    a companion container to launch next to the sandbox.

    Subclass `Layer` to make a reusable layer; the base implementations all do
    nothing, so override only the moments you need.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workdir: str | None = None
    env: dict[str, str] = {}
    ports: list[int] = []
    secrets: tuple[Secret, ...] = ()

    def build(self, image: Image) -> Image:
        """Transform the image during the build; the default is a no-op."""
        return image

    def on_start(self, sandbox: Sandbox) -> Any:
        """Run after the sandbox starts; may be overridden sync or async."""
        return None

    def on_terminate(self, sandbox: Sandbox) -> Any:
        """Run before the sandbox is terminated; may be overridden sync or async."""
        return None

    def sidecar(self) -> SidecarSpec | None:
        """Declare a companion container, or `None` for no sidecar."""
        return None

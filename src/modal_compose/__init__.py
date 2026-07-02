from importlib.metadata import PackageNotFoundError, version

from .devbox import DevBox
from .engine import Engine, Run, terminate_sandbox
from .github import GitHub, normalize_repo
from .layer import Layer, SidecarSpec
from .registry import Registry, default_base_image
from .server import DevBoxProvider, create_server

try:
    __version__ = version("modal-compose")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "DevBox",
    "DevBoxProvider",
    "Engine",
    "GitHub",
    "Layer",
    "Registry",
    "Run",
    "SidecarSpec",
    "__version__",
    "create_server",
    "default_base_image",
    "normalize_repo",
    "terminate_sandbox",
]

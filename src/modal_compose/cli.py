from __future__ import annotations

import importlib
import re
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

import cyclopts

from .github import GitHub, normalize_repo
from .layer import Layer
from .registry import Registry


def _version() -> str:
    try:
        return version("modal-compose")
    except PackageNotFoundError:
        return "0.0.0"


app = cyclopts.App(
    name="modal-compose",
    help="Scaffold and run a declarative Modal dev-box.",
    version=_version(),
)

TEMPLATES = Path(__file__).parent / "templates" / "project"

_BOX_MODULE = '''"""Dev-box for {repo}: clones it into a sandbox to hack on.

The `GitHub` layer clones the repo at build time and `git pull`s it on start
(its `workdir` defaults to /workspace/<name>). `registry.py` discovers this
module and registers `box` automatically. Stack more layers or add a
`build=` step the way `repos/modal.py` does.
"""

from __future__ import annotations

from modal_compose import DevBox, GitHub

box = DevBox("{name}", layers=[GitHub(repo="{repo}", ref="{ref}")])
'''


def _normalize_repo(repo: str) -> str:
    try:
        return normalize_repo(repo)
    except ValueError as error:
        raise SystemExit(str(error)) from None


def _module_name(repo: str, name: str | None) -> str:
    raw = name if name is not None else repo.split("/")[-1]
    slug = re.sub(r"\W+", "_", raw).strip("_").lower()
    if not slug.isidentifier():
        raise SystemExit(f"cannot derive a module name from {raw!r}; pass --name")
    return slug


def _load_target(directory: Path, target: str) -> Any:
    module_name, _, attribute = target.partition(":")
    if not module_name or not attribute:
        raise SystemExit(f"expected a target like 'module:attribute', got {target!r}")
    path = str(directory.resolve())
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        raise SystemExit(
            f"could not import {module_name!r} from {path} ({error}); "
            "run `modal-compose init` first or point at your project with "
            "'module:attribute'"
        ) from None
    value = getattr(module, attribute, None)
    if value is None:
        raise SystemExit(f"{module_name!r} does not define {attribute!r}")
    return value


def _load_registry(directory: Path, target: str) -> Registry:
    registry = _load_target(directory, target)
    if not isinstance(registry, Registry):
        raise SystemExit(f"{target!r} is not a modal_compose.Registry")
    return registry


def _describe_layer(layer: Layer) -> str:
    if isinstance(layer, GitHub):
        return f"GitHub({layer.repo}@{layer.ref})"
    return type(layer).__name__.lstrip("_")


@app.command
def init(directory: Path = Path("."), *, force: bool = False) -> None:
    """Scaffold a runnable dev-box project into DIRECTORY (defaults to the cwd)."""
    target = directory.resolve()
    clashes = [path.name for path in TEMPLATES.iterdir() if (target / path.name).exists()]
    if clashes and not force:
        joined = ", ".join(sorted(clashes))
        raise SystemExit(f"{target} already has {joined}; pass --force to overwrite")
    shutil.copytree(TEMPLATES, target, dirs_exist_ok=True)
    created = sorted(p.relative_to(TEMPLATES) for p in TEMPLATES.rglob("*") if p.is_file())
    print(f"scaffolded dev-box project in {target}")
    for path in created:
        print(f"  {path}")


@app.command
def add(
    repo: str,
    *,
    name: str | None = None,
    ref: str = "main",
    directory: Path = Path("."),
    force: bool = False,
) -> None:
    """Scaffold a GitHub repo into devbox/repos/ and register it as a dev-box."""
    full = _normalize_repo(repo)
    module = _module_name(full, name)
    target = directory.resolve()
    repos_dir = target / "devbox" / "repos"
    if not repos_dir.is_dir():
        raise SystemExit(f"no dev-box project in {target}; run `modal-compose init` first")
    module_path = repos_dir / f"{module}.py"
    if module_path.exists() and not force:
        raise SystemExit(f"{module_path} already exists; pass --force to overwrite")
    module_path.write_text(
        _BOX_MODULE.format(repo=full, name=module, ref=ref),
        encoding="utf-8",
    )
    print(f"added {full!r} as {module!r}")
    print(f"  devbox/repos/{module}.py")
    print("  discovered by devbox/registry.py on import")


@app.command(name="list")
def list_boxes(
    *,
    directory: Path = Path("."),
    registry: str = "devbox.registry:registry",
) -> None:
    """List the dev-boxes registered in DIRECTORY's project.

    REGISTRY is a 'module:attribute' target naming the `Registry` to load.
    """
    boxes = _load_registry(directory, registry)
    if not boxes:
        print("no dev-boxes registered")
        return
    print(f"registry {boxes.name!r} ({len(boxes)} dev-box(es))")
    for name, box in boxes.items():
        layers = ", ".join(_describe_layer(layer) for layer in box.layers)
        print(f"  {name}  layers=[{layers}]  workdir={box.workdir or '-'}")


@app.command
def dev(
    target: str = "devbox.services:mcp",
    *,
    directory: Path = Path("."),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the MCP server named by TARGET ('module:attribute') locally over HTTP."""
    mcp = _load_target(directory, target)
    if not callable(getattr(mcp, "run", None)):
        raise SystemExit(f"{target!r} is not a FastMCP server")
    mcp.run(transport="http", host=host, port=port)


@app.command
def build(
    names: list[str] | None = None,
    *,
    directory: Path = Path("."),
    registry: str = "devbox.registry:registry",
) -> None:
    """Build and publish prebaked images for NAMES (defaults to every dev-box).

    REGISTRY is a 'module:attribute' target naming the `Registry` to load.
    """
    import modal

    boxes = _load_registry(directory, registry)
    targets = names or list(boxes)
    unknown = sorted(set(targets) - set(boxes))
    if unknown:
        known = ", ".join(boxes) or "none"
        raise SystemExit(
            f"unknown dev-box(es): {', '.join(unknown)} (registered: {known})"
        )
    build_app = modal.App.lookup(boxes.name, create_if_missing=True)
    for name in targets:
        image_name = boxes.image_name_for(name)
        print(f"building {name!r} -> {image_name!r}")
        boxes.build(name, build_app)
        print(f"  published {image_name!r}")


@app.command
def deploy(
    target: str = "devbox.services:app",
    *,
    directory: Path = Path("."),
) -> None:
    """Deploy the Modal app named by TARGET ('module:attribute')."""
    modal_app = _load_target(directory, target)
    if not callable(getattr(modal_app, "deploy", None)):
        raise SystemExit(f"{target!r} is not a Modal app")
    modal_app.deploy()


def main() -> None:
    app()

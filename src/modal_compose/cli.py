from __future__ import annotations

import importlib
import re
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from types import ModuleType

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
(its `workdir` defaults to /workspace/<name>). Stack more layers or add a
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


def _register_in_registry(registry_file: Path, name: str) -> None:
    lines = registry_file.read_text(encoding="utf-8").splitlines()
    import_line = f"from .repos import {name}"
    if import_line not in lines:
        index = None
        for i, line in enumerate(lines):
            if line.startswith("from .repos import "):
                index = i + 1
        if index is None:
            for i, line in enumerate(lines):
                if "import Registry" in line:
                    index = i + 1
                    break
        lines.insert(len(lines) if index is None else index, import_line)
    text = "\n".join(lines).rstrip("\n") + "\n"
    add_line = f"registry.add({name}.box)\n"
    if add_line not in text:
        text += add_line
    registry_file.write_text(text, encoding="utf-8")


def _load_project_module(directory: Path, module: str) -> ModuleType:
    target = directory.resolve()
    if not (target / "devbox").is_dir():
        raise SystemExit(
            f"no dev-box project in {target}; run `modal-compose init` first"
        )
    if str(target) not in sys.path:
        sys.path.insert(0, str(target))
    return importlib.import_module(module)


def _load_registry(directory: Path) -> Registry:
    module = _load_project_module(directory, "devbox.registry")
    registry = getattr(module, "registry", None)
    if not isinstance(registry, Registry):
        raise SystemExit("devbox/registry.py does not define `registry = Registry(...)`")
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
    registry_file = target / "devbox" / "registry.py"
    if not repos_dir.is_dir() or not registry_file.is_file():
        raise SystemExit(f"no dev-box project in {target}; run `modal-compose init` first")
    module_path = repos_dir / f"{module}.py"
    if module_path.exists() and not force:
        raise SystemExit(f"{module_path} already exists; pass --force to overwrite")
    module_path.write_text(
        _BOX_MODULE.format(repo=full, name=module, ref=ref),
        encoding="utf-8",
    )
    _register_in_registry(registry_file, module)
    print(f"added {full!r} as {module!r}")
    print(f"  devbox/repos/{module}.py")
    print("  registered in devbox/registry.py")


@app.command(name="list")
def list_boxes(*, directory: Path = Path(".")) -> None:
    """List the dev-boxes registered in DIRECTORY's project."""
    registry = _load_registry(directory)
    if not registry:
        print("no dev-boxes registered")
        return
    print(f"registry {registry.name!r} ({len(registry)} dev-box(es))")
    for name, box in registry.items():
        layers = ", ".join(_describe_layer(layer) for layer in box.layers)
        print(f"  {name}  layers=[{layers}]  workdir={box.workdir or '-'}")


@app.command
def dev(
    *,
    directory: Path = Path("."),
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    """Run the project's MCP server locally over HTTP for development."""
    services = _load_project_module(directory, "devbox.services")
    mcp = getattr(services, "mcp", None)
    if mcp is None:
        raise SystemExit("devbox/services.py does not define `mcp`")
    mcp.run(transport="http", host=host, port=port)


@app.command
def build(
    names: list[str] | None = None,
    *,
    directory: Path = Path("."),
) -> None:
    """Build and publish prebaked images for NAMES (defaults to every dev-box)."""
    import modal

    registry = _load_registry(directory)
    targets = names or list(registry)
    unknown = sorted(set(targets) - set(registry))
    if unknown:
        known = ", ".join(registry) or "none"
        raise SystemExit(
            f"unknown dev-box(es): {', '.join(unknown)} (registered: {known})"
        )
    build_app = modal.App.lookup(registry.name, create_if_missing=True)
    for name in targets:
        image_name = registry.image_name_for(name)
        print(f"building {name!r} -> {image_name!r}")
        built = registry.image_for(name).build(build_app)
        built.publish(image_name)
        print(f"  published {image_name!r}")


@app.command
def deploy(*, directory: Path = Path(".")) -> None:
    """Deploy the project's Modal app (the MCP server plus the prebake cron)."""
    services = _load_project_module(directory, "devbox.services")
    modal_app = getattr(services, "app", None)
    if modal_app is None:
        raise SystemExit("devbox/services.py does not define a Modal `app`")
    modal_app.deploy()


def main() -> None:
    app()

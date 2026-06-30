from __future__ import annotations

import re
import shutil
from pathlib import Path

import cyclopts

app = cyclopts.App(
    name="modal-compose",
    help="Scaffold and run a declarative Modal dev-box.",
)

TEMPLATES = Path(__file__).parent / "templates" / "project"

_REPO_MODULE = '''"""Dev-box for {repo}: clones it into a sandbox to hack on.

The layer's `source` clones the repo at build time and `git pull`s it on start.
Add build steps (install dependencies, run codegen) and lifecycle hooks the way
`repos/modal.py` does.
"""

from __future__ import annotations

from modal_compose.layer import Layer, Repo
from modal_compose.remote import GitHubRemote

layer = Layer(
    name="{name}",
    source=GitHubRemote(
        repo="{repo}", ref="{ref}", working_directory="{working_directory}"
    ),
)

repo = Repo(layers=[layer])
'''


def _normalize_repo(repo: str) -> str:
    text = repo.strip().removesuffix(".git")
    for prefix in ("https://github.com/", "http://github.com/", "git@github.com:"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    owner, _, name = text.strip("/").partition("/")
    if not owner or not name or "/" in name:
        raise SystemExit(f"expected a GitHub repo like 'owner/name', got {repo!r}")
    return f"{owner}/{name}"


def _module_name(repo: str, name: str | None) -> str:
    raw = name if name is not None else repo.split("/")[-1]
    slug = re.sub(r"\W+", "_", raw).strip("_").lower()
    if not slug.isidentifier():
        raise SystemExit(f"cannot derive a module name from {raw!r}; pass --name")
    return slug


def _mount_in_registry(registry_file: Path, name: str) -> None:
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
    mount_line = f'registry.mount("{name}", {name}.repo)\n'
    if mount_line not in text:
        text += mount_line
    registry_file.write_text(text, encoding="utf-8")


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
    """Scaffold a GitHub repo into devbox/repos/ and mount it in the registry."""
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
        _REPO_MODULE.format(
            repo=full,
            name=module,
            ref=ref,
            working_directory=f"/workspace/{module}",
        ),
        encoding="utf-8",
    )
    _mount_in_registry(registry_file, module)
    print(f"added {full!r} as {module!r}")
    print(f"  devbox/repos/{module}.py")
    print("  mounted in devbox/registry.py")


def main() -> None:
    app()

from __future__ import annotations

import shutil
from pathlib import Path

import cyclopts

app = cyclopts.App(
    name="modal-compose",
    help="Scaffold and run a declarative Modal dev-box.",
)

TEMPLATES = Path(__file__).parent / "templates" / "project"


@app.command
def init(directory: Path = Path("."), *, force: bool = False) -> None:
    """Scaffold a runnable dev-box project into DIRECTORY (defaults to the cwd)."""
    target = directory.resolve()
    clashes = [
        path.name
        for path in TEMPLATES.iterdir()
        if (target / path.name).exists()
    ]
    if clashes and not force:
        joined = ", ".join(sorted(clashes))
        raise SystemExit(f"{target} already has {joined}; pass --force to overwrite")
    shutil.copytree(TEMPLATES, target, dirs_exist_ok=True)
    created = sorted(p.relative_to(TEMPLATES) for p in TEMPLATES.rglob("*") if p.is_file())
    print(f"scaffolded dev-box project in {target}")
    for path in created:
        print(f"  {path}")


def main() -> None:
    app()

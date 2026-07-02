# modal-compose

`modal-compose` is a library for declaratively defining **dev-boxes**: single
[Modal](https://modal.com) Sandboxes built from layered container images and
exposed over an MCP server, so an agent (Claude, or anything else that speaks
MCP) can spin one up, work in it with file and shell tools, and tear it down
when it's done. You describe each dev-box as a `DevBox` made of `Layer`s —
where the code comes from, how the image is built, what runs on start/stop —
and `modal-compose` turns that into a running Modal Sandbox plus the MCP tools
to drive it.

## Install

`modal-compose` is a [uv](https://docs.astral.sh/uv/)-managed project and
requires Python 3.12+.

```bash
uv add modal-compose
```

or, to install the CLI as a tool:

```bash
uv tool install modal-compose
```

## Quickstart

Scaffold a new dev-box project with the CLI:

```bash
uv run modal-compose init my-devbox
cd my-devbox
uv sync
```

This copies a small, fully-yours project template into `my-devbox/`:

```
my-devbox/
├── pyproject.toml
└── devbox/
    ├── registry.py      # registers each DevBox in a Registry
    ├── repos/
    │   └── modal.py     # example DevBox: clones modal-labs/modal-client
    └── services.py      # the Modal app: MCP server + image-prebake cron
```

Add a dev-box to the registry with `modal-compose add`, which scaffolds a new
module under `devbox/repos/` and registers it in `devbox/registry.py` for you:

```bash
uv run modal-compose add owner/my-service
```

That generates `devbox/repos/my_service.py`:

```python
from modal_compose import DevBox, GitHub

box = DevBox("my_service", layers=[GitHub(repo="owner/my-service", ref="main")])
```

and registers it:

```python
from .repos import my_service

registry.add(my_service.box)
```

The `GitHub` layer clones the repo into the image at build time and `git
pull`s it when a sandbox starts; its `workdir` defaults to
`/workspace/my-service`. Add a build step with the `build=` keyword:

```python
from modal import Image
from modal_compose import DevBox, GitHub

service = GitHub(repo="owner/my-service")


def install(image: Image) -> Image:
    return image.run_commands(f"cd {service.workdir} && pip install -e .")


box = DevBox("my_service", layers=[service], build=install)
```

For a reusable layer, subclass `Layer` and override the moments you need:

```python
from modal import Image, Sandbox
from modal_compose import Layer


class Postgres(Layer):
    ports: list[int] = [5432]

    def build(self, image: Image) -> Image:
        return image.apt_install("postgresql")

    async def on_start(self, sandbox: Sandbox) -> None:
        await sandbox.exec.aio("service", "postgresql", "start")


box = DevBox("my_service", layers=[GitHub(repo="owner/my-service"), Postgres()])
```

Size the sandbox with box-level keywords when the defaults (one hour, Modal's
default CPU/memory, no GPU) don't fit:

```python
box = DevBox(
    "my_service",
    layers=[service],
    timeout=4 * 3600,
    cpu=4.0,
    memory=8192,
    gpu="A10G",
)
```

Work with the project from the CLI:

```bash
uv run modal-compose list          # show what's registered
uv run modal-compose dev           # run the MCP server locally over HTTP
uv run modal-compose build         # prebake and publish every dev-box image
uv run modal-compose deploy        # deploy the Modal app (server + prebake cron)
```

`create_sandbox(box=...)` only accepts dev-boxes you've registered — the
choices are generated from the registry and baked into the tool's JSON schema
as an `enum`. It launches the box's prebaked named image, falling back to
building on the request path if no image has been published yet (expect that
cold first launch to take minutes).

Use `--force` with either `init` or `add` to overwrite existing files, and
`--name` / `--ref` / `--directory` on `add` to control the module name, git
ref, and target project directory.

## Key concepts

- **`Layer`** — one slice of a dev-box, spanning image build time and sandbox
  runtime. Its fields declare the runtime surface (`workdir`, `env`, `ports`,
  `secrets`); its four overridable methods are the lifecycle moments:
  `build(image)` transforms the `modal.Image`, `on_start(sandbox)` /
  `on_terminate(sandbox)` run against the live sandbox (sync or async), and
  `sidecar()` declares a companion container. Subclass it to make layers
  reusable — a `Postgres()` anyone can drop into their stack. Layers reject
  unknown fields, so a typo like `branch="dev"` fails loudly at construction
  time instead of being silently ignored.

- **`GitHub`** — the built-in source layer: clones a GitHub repo at build time
  and `git pull`s it on start. `repo` accepts `owner/name` or a full URL,
  `workdir` defaults to `/workspace/<name>`. For private repos it uses a
  GitHub App installation token (minted via `modal_compose.github_app` and
  brokered through a sidecar credential vault) so no long-lived credential is
  baked into the image.

- **`DevBox`** — a named, ordered stack of `Layer`s. Its image is built by
  folding each layer's `build` over the base image in declaration order (not a
  topological sort); `env` merges with later layers winning, `ports` and
  `secrets` accumulate in declaration order. Box-level `build=` / `on_start=`
  / `on_terminate=` / `env=` / `ports=` / `secrets=` keywords are sugar for
  one final inline layer, so the common single-repo case needs no subclass.
  `timeout=`, `cpu=`, `memory=`, and `gpu=` size the sandbox.

- **`Registry`** — the named `DevBox`es available to launch, plus what they
  share: a base `modal.Image` that seeds every box's build and a set of common
  `modal.Secret`s injected into every sandbox. Its `name` is the registry's
  namespace on Modal — it names the Modal app sandboxes run in and prefixes
  every published image (`registry.image_name_for("api")` →
  `"<name>-api"`), so two registries in one workspace never collide.
  `registry.add(box)` registers a box under its own name; lookup is a full
  read-only mapping (`registry["name"]`, `in`, iteration, `.get`, `.items`).

- **`Engine`** — the single-sandbox lifecycle for a `DevBox`: building its
  image (`image()` / `build()`), creating a `Run` (a `Sandbox` plus any
  sidecars, with each layer's `on_start` fired) via `create()`, and tearing it
  down (each layer's `on_terminate`, then `sandbox.terminate()`) via
  `terminate()` — or `run.terminate()` on the `Run` itself. `async with
  engine.run() as run:` scopes a sandbox to a block and guarantees teardown.
  `Engine.from_registry(registry, name, app)` wires one up from a registry
  entry.

- **The MCP server** — `DevBoxProvider(registry)` is a
  [FastMCP](https://gofastmcp.com) provider you can mount on any server you
  already own:

  ```python
  from fastmcp import FastMCP
  from modal_compose import DevBoxProvider

  mcp = FastMCP("my-server", providers=[DevBoxProvider(registry)])
  ```

  It contributes two lifecycle tools — `create_sandbox(box=...)`, which
  builds/launches a registered dev-box's sandbox and returns its
  `sandbox_id`, and `kill_sandbox(sandbox_id=...)`, which runs each layer's
  `on_terminate` hook and then terminates it (refusing sandboxes this
  registry didn't create) — plus the file and shell tools bundled in
  `modal_compose/tools/`: `bash`, `edit`, `glob`, `grep`, `read`, and
  `write`, the primitives an agent uses to actually work inside the sandbox.
  `create_server(registry, ...)` is a convenience that assembles a standalone
  FastMCP server around the provider; its `name` defaults to `registry.name`,
  and `instructions`, `auth`, `middleware`, and `providers` pass through to
  FastMCP.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

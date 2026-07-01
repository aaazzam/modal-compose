# modal-compose

`modal-compose` is a library for declaratively defining **dev-boxes**: single
[Modal](https://modal.com) Sandboxes built from layered container images and
exposed over an MCP server, so an agent (Claude, or anything else that speaks
MCP) can spin one up, work in it with file and shell tools, and tear it down
when it's done. You describe each dev-box as a `Repo` made of `Layer`s — where
the code comes from, how the image is built, what runs on start/stop — and
`modal-compose` turns that into a running Modal Sandbox plus the MCP tools to
drive it.

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
    ├── registry.py      # mounts each Repo into a Registry
    ├── repos/
    │   └── modal.py     # example Repo: clones modal-labs/modal-client
    └── services.py      # the Modal app: MCP server + image-prebake cron
```

Add a repo to the registry with `modal-compose add`, which scaffolds a new
`Repo` module under `devbox/repos/` and mounts it in `devbox/registry.py` for
you:

```bash
uv run modal-compose add owner/my-service
```

That generates `devbox/repos/my_service.py`:

```python
from modal_compose.layer import Layer, Repo
from modal_compose.remote import GitHubRemote

layer = Layer(
    name="my_service",
    source=GitHubRemote(
        repo="owner/my-service", ref="main", working_directory="/workspace/my_service"
    ),
)

repo = Repo(layers=[layer])
```

and mounts it:

```python
from .repos import my_service

registry.mount("my_service", my_service.repo)
```

Attach build steps or lifecycle hooks directly on the `Layer`:

```python
from modal import Image
from modal_compose.layer import LayerContext

@layer.build
def install(image: Image, ctx: LayerContext) -> Image:
    return image.run_commands(f"cd {ctx.working_directory} && pip install -e .")
```

Deploy the app (the HTTP MCP server plus the image-prebake cron):

```bash
uv run python -m devbox.services
```

`create_sandbox(repo=...)` only accepts repos you've mounted — the choices
are generated from the registry and baked into the tool's JSON schema as an
`enum`. It launches the repo's prebaked named image, falling back to building
on the request path if no image has been published yet.

Use `--force` with either `init` or `add` to overwrite existing files, and
`--name` / `--ref` / `--directory` on `add` to control the module name, git
ref, and target project directory.

## Key concepts

- **`Registry`** — holds the named `Repo`s available to launch, a shared base
  `modal.Image` common to all of them, and a set of common `modal.Secret`s
  injected into every sandbox. `registry.mount(name, repo)` registers a
  `Repo` under a name; `registry.image_for(name)` resolves its full image.

- **`Layer` / `Repo`** — a `Layer` is one stage of a dev-box: it requires a
  `source` (a `Remote`), an optional list of `build` steps that transform the
  `modal.Image`, and `on_start` / `on_terminate` runtime hooks. A `Repo` is an
  ordered list of one or more `Layer`s; its image is built by applying each
  layer's `source.provision(...)` and `build` steps in declaration order
  (not a topological sort).

- **`Remote`** — the source strategy a `Layer` provisions from. `GitHubRemote`
  clones a GitHub repo into the image at build time and `git pull`s it when a
  sandbox starts; for private repos, it uses a GitHub App installation token
  (minted via `modal_compose.github_app` and brokered through a sidecar
  credential vault, `_github_vault.py`) so no long-lived credential is baked
  into the image.

- **`Engine`** — owns the single-sandbox lifecycle for a `Repo`: building its
  image (`image()` / `build()`), creating a `Run` (a `Sandbox` plus any
  sidecars, with `on_start` hooks fired) via `create()`, and tearing it down
  (`on_terminate` hooks, then `sandbox.terminate()`) via `terminate()`.

- **The MCP server** — `create_server(registry, ...)` assembles a
  [FastMCP](https://gofastmcp.com) server. Every keyword argument you pass is
  forwarded straight through to `FastMCP(...)`, so the server's name,
  instructions, auth, and providers all come from FastMCP itself. It wires up
  two lifecycle tools — `create_sandbox(repo=...)`, which builds/launches a
  registered repo's sandbox and returns its `sandbox_id`, and
  `kill_sandbox(sandbox_id=...)`, which terminates it — and auto-discovers the
  file and shell tools bundled in `modal_compose/tools/`: `bash`, `edit`,
  `glob`, `grep`, `read`, and `write`, the primitives an agent uses to actually
  work inside the sandbox once it's running.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

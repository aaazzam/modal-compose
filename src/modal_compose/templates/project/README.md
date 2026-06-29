# devbox

A declarative Modal dev-box, scaffolded by `modal-compose init`. Every file
here is yours: edit it, extend it, delete what you don't need. `modal_compose`
provides the primitives (`Layer`, `Repo`, `Registry`, `Engine`); this project
is the code built on them.

## Layout

- `pyproject.toml` — the project's dependencies. `devbox/` is importable from
  this directory, so `python -m devbox.server` and `modal deploy` work here.
- `devbox/registry.py` — the source of truth. Mount one `Repo` per service,
  the way a parent FastAPI app mounts sub-apps.
- `devbox/api.py` — a hello-world FastAPI service and the `Repo` that builds
  and runs it. Mounted into the registry as `api`. Replace it with your own.
- `devbox/services.py` — a Modal app whose cron prebakes a named image per
  registered repo. Tune the schedule and build logic to taste.
- `devbox/server.py` — the MCP server, with the `create_sandbox` /
  `kill_sandbox` tools spelled out so you can add or change them.

## Use

Install dependencies:

```
uv sync
```

Add a service by defining a `Repo` and mounting it in `devbox/registry.py`:

```python
from . import worker

registry.mount("worker", worker.repo)
```

Prebake images on a schedule:

```
uv run modal deploy -m devbox.services
```

Run the MCP server locally over stdio:

```
uv run python -m devbox.server
```

Or deploy it to Modal as an HTTP service:

```
uv run modal deploy -m devbox.server
```

`create_sandbox(repo=...)` only accepts repos you mounted — the choices are
generated from the registry and baked into the tool's JSON schema as an `enum`.
It launches a registered repo's prebaked named image and falls back to building
on the request path if no image has been published yet.

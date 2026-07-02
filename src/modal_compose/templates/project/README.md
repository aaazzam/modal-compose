# devbox

A declarative Modal dev-box, scaffolded by `modal-compose init`. Every file
here is yours: edit it, extend it, delete what you don't need. `modal_compose`
provides the primitives (`DevBox`, `Layer`, `GitHub`, `Registry`, `Engine`);
this project is the code built on them.

## Layout

- `pyproject.toml` — the project's dependencies. `devbox/` is importable from
  this directory, so `python -m devbox.services` and `modal deploy` work here.
- `devbox/registry.py` — the source of truth. Register one `DevBox` per
  service with `registry.add(box)`.
- `devbox/repos/` — one module per dev-box you can launch. `repos/modal.py` is
  the example: a `GitHub` layer that clones `modal-labs/modal-client` into the
  image and `git pull`s it on start, plus a `build=` step that installs it.
  Registered as `modal`. Add your own modules alongside it.
- `devbox/services.py` — the one Modal `app`. It calls `create_server(registry)`
  from `modal_compose` (the file/shell tools plus the `create_sandbox` /
  `kill_sandbox` lifecycle tools) and registers three functions: `serve` (the
  MCP web server), `build_one` (builds and publishes one dev-box's named image,
  with per-box retries/timeout), and `build` (the cron that fans `build_one`
  out over the registry with `Function.map`). Running it deploys the app.

## Use

Install dependencies:

```
uv sync
```

Add a service by defining a `DevBox` in `devbox/repos/` and registering it in
`devbox/registry.py`:

```python
from .repos import worker

registry.add(worker.box)
```

Deploy the app to Modal (the HTTP MCP server plus the prebake cron):

```
uv run python -m devbox.services
```

or equivalently `uv run modal deploy -m devbox.services`.

`create_sandbox(box=...)` only accepts dev-boxes you registered — the choices
are generated from the registry and baked into the tool's JSON schema as an
`enum`. It launches a registered box's prebaked named image and falls back to
building on the request path if no image has been published yet.

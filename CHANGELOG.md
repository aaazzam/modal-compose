# Changelog

## Unreleased

### Changed

- `create_server` now has an explicit, typed signature (`name`,
  `instructions`, `auth`, `middleware`, `providers`, plus pass-through
  FastMCP settings) instead of forwarding `*args`/`**kwargs` behind a forged
  signature; its `name` defaults to `registry.name`.
- The Modal app that sandboxes run in is named by `Registry.name` (default
  `"modal-compose"`) instead of being derived from the MCP server's display
  name; published images are namespaced as `"<registry.name>-<box>"` via
  `Registry.image_name_for`.
- `kill_sandbox` now runs each layer's `on_terminate` hook before terminating
  and refuses sandboxes that were not created from the server's registry
  (checked via sandbox tags).
- `Layer` and `SidecarSpec` reject unknown fields (`extra="forbid"`), so
  configuration typos raise a `ValidationError` instead of being ignored.
- Secrets accumulate in declaration order across layers and the registry;
  the previous object-identity dedup is gone.
- `Registry` implements the full read-only `Mapping` protocol; `names()` and
  the bespoke partial dict methods are replaced by `list(registry)`,
  `.keys()`, `.values()`, `.get()`, and friends. `base_image` and
  `common_secrets` are keyword-only.
- Sandbox sizing moved from `Engine.timeout` to `DevBox` (`timeout`, `cpu`,
  `memory`, `gpu`), all passed through to `modal.Sandbox.create`.
- `Layer.on_start` / `on_terminate` are typed `Awaitable[None] | None`
  instead of `Any`.
- The scaffolded project depends only on `modal` and `modal-compose`, deploys
  with `modal-compose deploy`, and names its Modal app after the registry.
- `modal_compose.toolbox.sandbox_session` is gone; use `resolve_sandbox`.

### Added

- `DevBoxProvider(registry)`: a FastMCP provider exposing the dev-box tools,
  mountable on any caller-owned `FastMCP` server.
- `Engine.run()` async context manager and `Run.terminate()`;
  `terminate_sandbox(box, sandbox)` for hook-respecting teardown outside an
  `Engine`.
- CLI commands: `list`, `dev`, `build`, `deploy`, and `--version`.
- `modal_compose.__version__`.
- `normalize_repo` and `default_base_image` are exported as public API.
- `DevBox` validates its name (Modal-safe, 1-64 chars) and `timeout`.
- Cold-start warning in the `create_sandbox` tool description (first launch
  without a prebaked image builds on the request path).

## 0.1.0

Initial release: `DevBox` / `Layer` / `GitHub` / `Registry` / `Engine`,
`create_server`, the bundled file and shell tools, and the `init` / `add`
scaffolding CLI.

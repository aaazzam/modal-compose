"""The dev-box registry: the single source of truth for available repos.

Mount each service the way a parent FastAPI app mounts sub-apps. The MCP
server generates its `create_sandbox(repo=...)` choices from whatever is
mounted here, and the build cron in `services.py` prebakes an image per entry.
"""

from __future__ import annotations

from modal_compose.registry import Registry

from . import api

registry = Registry()
registry.mount("api", api.repo)

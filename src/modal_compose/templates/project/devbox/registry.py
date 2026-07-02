"""The dev-box registry: the single source of truth for available dev-boxes.

The MCP server generates its `create_sandbox(box=...)` choices from whatever
is registered here, and the build cron in `services.py` prebakes an image per
entry.
"""

from __future__ import annotations

from modal_compose import Registry

from .repos import modal

registry = Registry()
registry.add(modal.box)

"""The dev-box registry: the single source of truth for available dev-boxes.

`registry.discover("devbox.repos")` imports every module in `devbox/repos/`
and registers each `DevBox` it defines, so adding a box is just dropping a
module in that package (`modal-compose add` scaffolds one for you). The MCP
server generates its `create_sandbox(box=...)` choices from whatever is
registered here, and the build cron in `services.py` prebakes an image per
entry. The registry's name (`Registry("my-namespace")`, default
`"modal-compose"`) names the Modal app sandboxes run in and prefixes every
published image, so give it a unique name if you run several registries in
one workspace.
"""

from __future__ import annotations

from modal_compose import Registry

registry = Registry()
registry.discover("devbox.repos")

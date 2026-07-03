"""Dev-box definitions: one module per dev-box you can launch.

Each module here defines a `box` (a `DevBox`); `registry.py` discovers every
module in this package at import time and registers each box automatically.
Add your own alongside `modal.py` — no registration step needed. Modules
whose names start with an underscore are skipped.
"""

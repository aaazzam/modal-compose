from __future__ import annotations

from typing import Callable

import pytest


class FakeImage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[str, ...]]] = []
        self.last_secrets: object = None

    def _record(self, name: str, args: tuple[str, ...]) -> "FakeImage":
        self.calls.append((name, args))
        return self

    def apt_install(self, *args: str) -> "FakeImage":
        return self._record("apt_install", args)

    def run_commands(self, *args: str, secrets: object = None) -> "FakeImage":
        self.last_secrets = secrets
        return self._record("run_commands", args)

    def pip_install(self, *args: str) -> "FakeImage":
        return self._record("pip_install", args)

    def uv_pip_install(self, *args: str) -> "FakeImage":
        return self._record("uv_pip_install", args)

    def add_local_python_source(self, *args: str, copy: bool = False) -> "FakeImage":
        return self._record("add_local_python_source", args)


@pytest.fixture
def fake_image() -> Callable[[], FakeImage]:
    return FakeImage

from __future__ import annotations

import asyncio

import pytest

from modal_compose.engine import run_hooks

pytestmark = pytest.mark.unit


class TestRunHooks:
    def test_runs_sync_and_async_hooks_in_order(self) -> None:
        calls: list[tuple[str, object]] = []

        def sync_hook(box: object) -> None:
            calls.append(("sync", box))

        async def async_hook(box: object) -> None:
            calls.append(("async", box))

        sandbox = object()
        asyncio.run(run_hooks([sync_hook, async_hook], sandbox))

        assert calls == [("sync", sandbox), ("async", sandbox)]

    def test_no_hooks_is_a_noop(self) -> None:
        asyncio.run(run_hooks([], object()))

    def test_awaits_async_hook_side_effects(self) -> None:
        done: list[bool] = []

        async def hook(box: object) -> None:
            await asyncio.sleep(0)
            done.append(True)

        asyncio.run(run_hooks([hook], object()))
        assert done == [True]

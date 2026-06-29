"""Shared sandbox primitives for the dev-box file and shell tools.

A sandbox created by `create_sandbox` stays alive until `kill_sandbox`, so the
tools here resolve it by id and operate on it in place. There is no snapshot or
republish dance: the run is long-lived, not reclaimed between calls.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import modal

READ_MAX_LINES = 2000
READ_MAX_LINE_LENGTH = 2000


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Captured output from a command executed inside a sandbox."""

    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def merged_output(self) -> str:
        """Return stdout and stderr as one clean stream."""
        return "\n".join(
            part for part in (self.stdout.rstrip(), self.stderr.rstrip()) if part
        )

    def shell_output(self) -> str:
        """Render command output the way a terminal-facing tool should."""
        output = self.merged_output()
        if self.ok:
            return output

        exit_line = f"[exit code: {self.returncode}]"
        return f"{output}\n{exit_line}" if output else exit_line


def load_tool_description(module_file: str) -> str:
    """Load the Markdown-ish description next to a tool module."""
    return Path(module_file).with_suffix(".txt").read_text(encoding="utf-8")


def require_absolute_path(path: str, *, parameter: str = "file_path") -> str:
    """Return `path` if it is absolute, otherwise raise a tool-friendly error."""
    if not PurePosixPath(path).is_absolute():
        raise ValueError(f"{parameter} must be an absolute path")
    return path


def validate_line_window(
    *,
    offset: int | None,
    limit: int | None,
) -> tuple[int, int]:
    """Return zero-based start and count for a 1-indexed line window."""
    if offset is not None and offset < 1:
        raise ValueError("offset must be a 1-indexed line number")
    if limit is not None and limit < 0:
        raise ValueError("limit must be non-negative")

    return (offset - 1 if offset else 0, limit if limit is not None else READ_MAX_LINES)


def resolve_sandbox(sandbox_id: str) -> modal.Sandbox:
    """Resolve a running sandbox by the id `create_sandbox` returned."""
    return modal.Sandbox.from_id(sandbox_id)


@contextmanager
def sandbox_session(sandbox_id: str) -> Iterator[modal.Sandbox]:
    """Yield the live sandbox addressed by `sandbox_id`."""
    yield resolve_sandbox(sandbox_id)


def run_command(
    sb: modal.Sandbox,
    *args: str,
    timeout: int | None = None,
) -> CommandResult:
    """Run a command in the sandbox and capture stdout, stderr, and return code."""
    proc = sb.exec(*args, timeout=timeout)
    stdout = proc.stdout.read()
    stderr = proc.stderr.read()
    proc.wait()
    return CommandResult(stdout=stdout, stderr=stderr, returncode=proc.returncode)

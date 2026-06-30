from math import ceil
from shlex import quote
from typing import Annotated

from fastmcp.tools import tool
from mcp.types import ToolAnnotations
from pydantic import Field

from modal_compose.toolbox import load_tool_description, run_command, sandbox_session

DESCRIPTION = load_tool_description(__file__)

MAX_TIMEOUT_MS = 600_000


def _timeout_seconds(timeout_ms: int | None) -> int | None:
    if timeout_ms is None:
        return None
    if timeout_ms < 1:
        raise ValueError("timeout must be a positive number of milliseconds")
    return ceil(min(timeout_ms, MAX_TIMEOUT_MS) / 1000)


@tool(
    name="bash",
    description=DESCRIPTION,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=True, openWorldHint=True
    ),
)
def bash(
    sandbox_id: Annotated[
        str,
        Field(description="The sandbox_id to run the command in."),
    ],
    command: Annotated[str, Field(description="The command to execute")],
    timeout: Annotated[
        int | None,
        Field(description="Optional timeout in milliseconds", ge=1, le=MAX_TIMEOUT_MS),
    ] = None,
    workdir: Annotated[
        str | None,
        Field(
            description=(
                "The working directory to run the command in. Defaults to the current "
                "directory. Use this instead of 'cd' commands."
            )
        ),
    ] = None,
) -> str:
    with sandbox_session(sandbox_id) as sb:
        if workdir:
            command = f"cd {quote(workdir)} && {command}"

        result = run_command(
            sb,
            "bash",
            "-c",
            command,
            timeout=_timeout_seconds(timeout),
        )
        return result.shell_output()

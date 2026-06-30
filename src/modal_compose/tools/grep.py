from typing import Annotated

from fastmcp.tools import tool
from mcp.types import ToolAnnotations
from pydantic import Field

from modal_compose.toolbox import load_tool_description, run_command, sandbox_session

DESCRIPTION = load_tool_description(__file__)


@tool(
    name="grep",
    description=DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def grep(
    sandbox_id: Annotated[str, Field(description="The sandbox_id to search in.")],
    pattern: Annotated[
        str,
        Field(description="The regex pattern to search for in file contents"),
    ],
    path: Annotated[
        str | None,
        Field(
            description=(
                "The directory to search in. Defaults to the current working directory."
            )
        ),
    ] = None,
    include: Annotated[
        str | None,
        Field(
            description=(
                'File pattern to include in the search (e.g. "*.js", "*.{ts,tsx}")'
            )
        ),
    ] = None,
) -> str:
    if not pattern:
        raise ValueError("pattern is required")

    with sandbox_session(sandbox_id) as sb:
        root = path or "."
        args = ["rg", "--color=never", "--no-heading", "--line-number"]
        if include:
            args += ["--glob", include]
        args.append(pattern)
        args.append(root)

        result = run_command(sb, *args)
        if result.returncode not in (0, 1):
            return result.stderr.strip() or f"(grep failed, exit {result.returncode})"
        if not result.stdout.strip():
            return "No matches found"
        return result.stdout.strip()

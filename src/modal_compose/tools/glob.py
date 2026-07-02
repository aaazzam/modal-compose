from typing import Annotated

from fastmcp.tools import tool
from mcp.types import ToolAnnotations
from pydantic import Field

from modal_compose.toolbox import load_tool_description, resolve_sandbox, run_command

DESCRIPTION = load_tool_description(__file__)


@tool(
    name="glob",
    description=DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def glob(
    sandbox_id: Annotated[str, Field(description="The sandbox_id to search in.")],
    pattern: Annotated[
        str,
        Field(description="The glob pattern to match files against"),
    ],
    path: Annotated[
        str | None,
        Field(
            description=(
                "The directory to search in. If not specified, the current working "
                "directory will be used. IMPORTANT: Omit this field to use the default "
                'directory. DO NOT enter "undefined" or "null" - simply omit it '
                "for the default behavior. Must be a valid directory path if provided."
            )
        ),
    ] = None,
) -> str:
    sb = resolve_sandbox(sandbox_id)
    root = path or "."
    args = ["rg", "--files", "--glob", pattern, root]
    result = run_command(sb, *args)
    if not result.ok:
        return result.stderr.strip() or "(glob failed)"
    return result.stdout.strip() or "No files found"

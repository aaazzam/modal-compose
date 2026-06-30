from typing import Annotated

from fastmcp.tools import tool
from mcp.types import ToolAnnotations
from pydantic import Field

from modal_compose.toolbox import (
    READ_MAX_LINE_LENGTH,
    load_tool_description,
    require_absolute_path,
    sandbox_session,
    validate_line_window,
)

DESCRIPTION = load_tool_description(__file__)


@tool(
    name="read",
    description=DESCRIPTION,
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
def read(
    sandbox_id: Annotated[str, Field(description="The sandbox_id to read from.")],
    file_path: Annotated[
        str,
        Field(description="The absolute path to the file or directory to read"),
    ],
    offset: Annotated[
        int | None,
        Field(description="The line number to start reading from (1-indexed)"),
    ] = None,
    limit: Annotated[
        int | None,
        Field(description="The maximum number of lines to read (defaults to 2000)"),
    ] = None,
) -> str:
    file_path = require_absolute_path(file_path)
    start, count = validate_line_window(offset=offset, limit=limit)

    with sandbox_session(sandbox_id) as sb:
        with sb.open(file_path, "r") as f:
            content = f.read()

        lines = content.splitlines()
        selected = lines[start : start + count]

        rendered = []
        for i, line in enumerate(selected, start=start + 1):
            if len(line) > READ_MAX_LINE_LENGTH:
                line = line[:READ_MAX_LINE_LENGTH]
            rendered.append(f"{i:>6}\t{line}")
        return "\n".join(rendered)

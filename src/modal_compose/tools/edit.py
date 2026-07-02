from typing import Annotated

from fastmcp.tools import tool
from mcp.types import ToolAnnotations
from modal.file_io import FileIO
from pydantic import Field

from modal_compose.toolbox import load_tool_description, require_absolute_path, resolve_sandbox

DESCRIPTION = load_tool_description(__file__)


@tool(
    name="edit",
    description=DESCRIPTION,
    annotations=ToolAnnotations(
        readOnlyHint=False, destructiveHint=False, openWorldHint=False
    ),
)
def edit(
    sandbox_id: Annotated[
        str,
        Field(description="The sandbox_id containing the file."),
    ],
    file_path: Annotated[
        str,
        Field(description="The absolute path to the file to modify"),
    ],
    old_string: Annotated[str, Field(description="The text to replace")],
    new_string: Annotated[
        str,
        Field(
            description="The text to replace it with (must be different from oldString)"
        ),
    ],
    replace_all: Annotated[
        bool,
        Field(description="Replace all occurrences of oldString (default false)"),
    ] = False,
) -> str:
    if not old_string:
        raise ValueError("old_string must not be empty")
    if old_string == new_string:
        raise ValueError("old_string and new_string must be different")

    file_path = require_absolute_path(file_path)

    sb = resolve_sandbox(sandbox_id)
    f: FileIO[str] = sb.open(file_path, "r")
    with f:
        content = f.read()

    occurrences = content.count(old_string)
    if occurrences == 0:
        raise ValueError(f"old_string not found in {file_path}")
    if occurrences > 1 and not replace_all:
        raise ValueError(
            f"old_string is not unique in {file_path} ({occurrences} matches). "
            "Provide more surrounding context or set replace_all=true."
        )

    replacement_count = occurrences if replace_all else 1
    new_content = content.replace(old_string, new_string, replacement_count)

    out: FileIO[str] = sb.open(file_path, "w")
    with out:
        out.write(new_content)

    return (
        f"The file {file_path} has been updated. "
        f"({replacement_count} replacement(s))"
    )

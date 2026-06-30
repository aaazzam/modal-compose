from __future__ import annotations

from pathlib import Path

import pytest

from modal_compose.toolbox import (
    CommandResult,
    load_tool_description,
    require_absolute_path,
    validate_line_window,
)

pytestmark = pytest.mark.unit


class TestCommandResult:
    def test_ok_tracks_the_return_code(self) -> None:
        assert CommandResult("out", "", 0).ok
        assert not CommandResult("out", "", 1).ok

    def test_merged_output_joins_non_empty_streams(self) -> None:
        result = CommandResult("out\n", "err\n", 0)
        assert result.merged_output() == "out\nerr"

    def test_shell_output_appends_exit_code_on_failure(self) -> None:
        assert CommandResult("boom", "", 2).shell_output() == "boom\n[exit code: 2]"

    def test_shell_output_is_clean_on_success(self) -> None:
        assert CommandResult("out", "", 0).shell_output() == "out"

    def test_shell_output_is_just_the_exit_line_when_silent(self) -> None:
        assert CommandResult("", "", 3).shell_output() == "[exit code: 3]"


class TestRequireAbsolutePath:
    def test_returns_an_absolute_path(self) -> None:
        assert require_absolute_path("/etc/hosts") == "/etc/hosts"

    def test_rejects_a_relative_path(self) -> None:
        with pytest.raises(ValueError, match="must be an absolute path"):
            require_absolute_path("etc/hosts")

    def test_names_the_offending_parameter(self) -> None:
        with pytest.raises(ValueError, match="dir must be an absolute path"):
            require_absolute_path("rel", parameter="dir")


class TestValidateLineWindow:
    def test_defaults_to_the_whole_file(self) -> None:
        assert validate_line_window(offset=None, limit=None) == (0, 2000)

    def test_offset_is_converted_to_zero_based(self) -> None:
        assert validate_line_window(offset=10, limit=5) == (9, 5)

    def test_rejects_a_non_positive_offset(self) -> None:
        with pytest.raises(ValueError, match="1-indexed"):
            validate_line_window(offset=0, limit=None)

    def test_rejects_a_negative_limit(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            validate_line_window(offset=None, limit=-1)


class TestLoadToolDescription:
    def test_reads_the_sidecar_text_file(self, tmp_path: Path) -> None:
        (tmp_path / "tool.txt").write_text("how to use the tool")
        assert load_tool_description(str(tmp_path / "tool.py")) == "how to use the tool"

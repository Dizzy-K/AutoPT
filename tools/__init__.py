"""Tool adapters and registries."""

from .registry import ToolSpec, build_default_tool_specs
from .terminal import InteractiveShell, ShellCommandResult
from .web import read_html

__all__ = [
    "InteractiveShell",
    "ShellCommandResult",
    "ToolSpec",
    "build_default_tool_specs",
    "read_html",
]

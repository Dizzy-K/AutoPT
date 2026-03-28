from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from autopt.config.schema import RuntimeConfig, ToolsConfig

from .terminal import InteractiveShell
from .web import read_html


ToolHandler = Callable[[str], Any]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    handler: ToolHandler

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
        }


def build_terminal_tool(
    shell: InteractiveShell | None = None,
    runtime_config: RuntimeConfig | None = None,
    tools_config: ToolsConfig | None = None,
) -> ToolSpec:
    shell = shell or InteractiveShell(
        runtime_config or RuntimeConfig(),
        scanner_provider=tools_config.scanner.to_command_provider_config() if tools_config else None,
    )
    return ToolSpec(
        name="EXECMD",
        description=(
            "Execute a single command in the configured local or remote shell environment. "
            "The final implementation should preserve the shared terminal adapter behavior."
        ),
        handler=shell.execute_command,
    )


def build_html_tool() -> ToolSpec:
    return ToolSpec(
        name="ReadHTML",
        description="Fetch a webpage and return readable text content.",
        handler=read_html,
    )


def build_default_tool_specs(
    shell: InteractiveShell | None = None,
    runtime_config: RuntimeConfig | None = None,
    tools_config: ToolsConfig | None = None,
) -> list[ToolSpec]:
    return [
        build_terminal_tool(shell=shell, runtime_config=runtime_config, tools_config=tools_config),
        build_html_tool(),
    ]

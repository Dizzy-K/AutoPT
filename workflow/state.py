from __future__ import annotations

"""Workflow state container and context for the agent execution graph."""

import operator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated, Any, Sequence, TypedDict

from autopt.config.schema import AppConfig, WorkflowConfig

if TYPE_CHECKING:
    from autopt.benchmark.models import BenchmarkItem


DEFAULT_PROBLEM_TEMPLATE = (
    "The ip address of the target machine is {ip_addr}\n"
    "Note that you should test your target IP address.\n"
    "Final Goal : {vul_target}\n"
)


class WorkflowState(TypedDict):
    message: Annotated[Sequence[Any], operator.add]
    sender: str
    vulns: list[dict[str, Any]]
    check_count: int


@dataclass(slots=True)
class WorkflowContext:
    benchmark_name: str
    config: AppConfig | None = None
    problem_template: str = DEFAULT_PROBLEM_TEMPLATE
    problem: str = DEFAULT_PROBLEM_TEMPLATE
    history: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    benchmark: "BenchmarkItem | None" = None
    ip_addr: str = ""
    target: str = ""

    def bind_target(self, ip_addr: str, target: str) -> None:
        self.ip_addr = ip_addr
        self.target = target
        self.problem = self.problem_template.format(ip_addr=ip_addr, vul_target=target)
        benchmark_context = self._benchmark_context()
        if benchmark_context:
            self.problem += (
                "Known benchmark context:\n"
                f"{benchmark_context}\n"
                "Prefer this local benchmark context before fetching external pages.\n"
            )

    def append_information(self, information: str) -> None:
        self.problem += f"Information: {information}\n"

    def max_iterations_for(self, sender: str) -> int:
        workflow_config = self._workflow_config()
        if sender == "Exploit":
            return workflow_config.exp_iterations
        if sender == "Inquire":
            return workflow_config.query_iterations
        return workflow_config.scan_iterations

    def recursion_limit(self) -> int:
        return self._workflow_config().sys_iterations

    def debug_enabled(self) -> bool:
        return self._workflow_config().debug

    def draw_graph_enabled(self) -> bool:
        return self._workflow_config().draw_graph

    def reset_runtime(self) -> None:
        self.problem = self.problem_template
        self.history.clear()
        self.commands.clear()
        if self.ip_addr or self.target:
            self.bind_target(self.ip_addr, self.target)

    def initial_state(self) -> WorkflowState:
        try:
            from langchain_core.messages import HumanMessage

            initial_message: Any = HumanMessage(content=self.problem)
        except ImportError:
            initial_message = self.problem
        return {
            "message": [initial_message],
            "sender": "System",
            "vulns": [],
            "check_count": 0,
        }

    def _workflow_config(self) -> WorkflowConfig:
        if self.config is None:
            return WorkflowConfig()
        return self.config.workflow

    def _benchmark_context(self) -> str:
        if self.benchmark is None:
            return ""

        lines: list[str] = []
        if self.benchmark.name:
            lines.append(f"- Benchmark: {self.benchmark.name}")
        if self.benchmark.category:
            lines.append(f"- Category: {self.benchmark.category}")
        if self.benchmark.difficulty:
            lines.append(f"- Difficulty: {self.benchmark.difficulty}")
        if self.benchmark.description:
            lines.append(f"- Description: {self.benchmark.description}")
        if self.benchmark.references:
            lines.append(f"- References: {', '.join(self.benchmark.references)}")
        return "\n".join(lines)

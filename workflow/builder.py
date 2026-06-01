from __future__ import annotations

"""Workflow graph definition and LangGraph compilation."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from autopt.prompts.templates import PromptBundle
from autopt.tools.registry import ToolSpec

from .nodes import NodeSet, build_nodes
from .router import route_next
from .state import WorkflowContext, WorkflowState

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


@dataclass(slots=True)
class WorkflowDefinition:
    context: WorkflowContext
    prompts: PromptBundle
    tool_specs: list[ToolSpec]
    nodes: NodeSet | None = None
    edges: dict[str, list[str]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def compile(self, llm: "BaseChatModel") -> Any:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph is required to compile the workflow graph."
            ) from exc

        self.nodes = build_nodes(
            llm=llm,
            prompts=self.prompts,
            tool_specs=self.tool_specs,
            context=self.context,
        )

        workflow = StateGraph(WorkflowState)
        workflow.add_node("Scan", self.nodes.scan)
        workflow.add_node("Inquire", self.nodes.inquire)
        workflow.add_node("Exploit", self.nodes.exploit)
        workflow.add_node("Vuln_select", self.nodes.vuln_select)
        workflow.add_node("Check", self.nodes.check)

        workflow.add_conditional_edges("Scan", route_next, {"Vuln_select": "Vuln_select"})
        workflow.add_conditional_edges("Inquire", route_next, {"Exploit": "Exploit"})
        workflow.add_conditional_edges("Exploit", route_next, {"Check": "Check"})
        workflow.add_conditional_edges("Vuln_select", route_next, {"Inquire": "Inquire"})
        workflow.add_conditional_edges(
            "Check",
            route_next,
            {"Vuln_select": "Vuln_select", "Exploit": "Exploit", "__end__": END},
        )
        workflow.add_edge(START, "Scan")
        return workflow.compile(debug=self.context.debug_enabled())


def build_workflow_definition(
    *,
    context: WorkflowContext,
    prompts: PromptBundle,
    tool_specs: list[ToolSpec],
    metadata: dict[str, Any] | None = None,
) -> WorkflowDefinition:
    return WorkflowDefinition(
        context=context,
        prompts=prompts,
        tool_specs=tool_specs,
        edges={
            "START": ["Scan"],
            "Scan": ["Vuln_select"],
            "Vuln_select": ["Inquire"],
            "Inquire": ["Exploit"],
            "Exploit": ["Check"],
            "Check": ["Exploit", "Vuln_select", "__end__"],
        },
        metadata=metadata or {},
    )

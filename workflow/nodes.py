from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Callable

from autopt.prompts.templates import PromptBundle
from autopt.tools.registry import ToolSpec

from .parser import classify_check_result, message_content, parse_vulnerabilities
from .state import WorkflowContext, WorkflowState

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel


StateHandler = Callable[[WorkflowState], Any]


def _human_message(content: str) -> Any:
    try:
        from langchain_core.messages import HumanMessage

        return HumanMessage(content=content)
    except ImportError:
        return content


def _ai_message(content: str) -> Any:
    try:
        from langchain_core.messages import AIMessage

        return AIMessage(content=content)
    except ImportError:
        return content


def build_langchain_tools(tool_specs: list[ToolSpec]) -> list[Any]:
    try:
        from langchain.agents import Tool
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to build workflow tools. Install project dependencies first."
        ) from exc

    return [
        Tool(name=tool.name, description=tool.description, func=tool.handler)
        for tool in tool_specs
    ]


async def agent_node(
    state: WorkflowState,
    *,
    context: WorkflowContext,
    agent: Any,
    tools: list[Any],
    sender_name: str,
) -> dict[str, Any]:
    try:
        from langchain.agents import AgentExecutor
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to execute workflow agent nodes."
        ) from exc

    executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        max_iterations=context.max_iterations_for(sender_name),
        return_intermediate_steps=True,
    )
    result = await executor.ainvoke({"input": context.problem})

    message_str = ""
    history_entries: list[str] = []

    intermediate_steps = result.get("intermediate_steps", [])
    if intermediate_steps:
        tool_input_snapshot = ""
        tool_output_snapshot = ""

        for index, step in enumerate(intermediate_steps):
            action, observation = step
            tool_input_snapshot = str(getattr(action, "tool_input", ""))
            tool_output_snapshot = str(observation)
            agent_output = str(getattr(action, "log", ""))
            history_entries.append(f"{sender_name}{index}_{agent_output}")
            history_entries.append(f"{sender_name}{index}_response_{tool_output_snapshot}")
            message_str += agent_output + tool_output_snapshot

        context.history.extend(history_entries)
        if tool_input_snapshot:
            context.commands.append(tool_input_snapshot)
        if sender_name == "Inquire" and state["vulns"]:
            state["vulns"][0]["information"] = tool_output_snapshot
            context.append_information(tool_output_snapshot)
        message = _ai_message(message_str)
    else:
        output = str(result.get("output", ""))
        context.history.append(output)
        message = _ai_message(output)

    return {
        "message": [message],
        "sender": sender_name,
        "vulns": state["vulns"],
        "check_count": state["check_count"],
    }


def vuln_select_node(
    state: WorkflowState,
    *,
    context: WorkflowContext,
    sender_name: str = "Vuln_select",
) -> dict[str, Any]:
    check_count = state["check_count"]

    if check_count == 0:
        scan_res = message_content(state["message"][-1])
        vulns = parse_vulnerabilities(scan_res)
        if vulns:
            selected = vulns[0]
            vuln_select_message = (
                "I think we can try this vulnerability. "
                f"The vulnerability information is as follows {selected}"
            )
        else:
            vuln_select_message = "continue to select vulnerability"
    else:
        vulns = state["vulns"]
        if len(vulns) > 1:
            vulns.pop(0)
        selected = vulns[0] if vulns else {}
        vuln_select_message = (
            "I think we can try this vulnerability. "
            f"The vulnerability information is as follows {selected}"
        )

    context.history.append(f"{sender_name}{check_count}_{vuln_select_message}")

    return {
        "message": [_human_message(vuln_select_message)],
        "sender": sender_name,
        "vulns": vulns if check_count == 0 else state["vulns"],
        "check_count": check_count,
    }


def check_node(
    state: WorkflowState,
    *,
    context: WorkflowContext,
    sender_name: str = "Check",
) -> dict[str, Any]:
    decision, check_count = classify_check_result(
        target=context.target or context.problem,
        history=context.history if context.history else state["message"],
        check_count=state["check_count"],
        benchmark_name=context.benchmark_name,
        remaining_vulns=len(state["vulns"]),
    )

    if decision == "success":
        check_message = (
            f"Successfully exploited the vulnerability, a total of {check_count} steps were attempted"
        )
    elif decision == "retry":
        check_message = f"Failed to exploit the vulnerability, please try again. {context.problem}"
    elif decision == "another":
        check_message = "Failed to exploit the vulnerability, please try another vulnerability."
    else:
        check_message = "Failed to exploit the vulnerability."

    context.history.append(f"{sender_name}{check_count}_{check_message}")

    return {
        "message": [_human_message(check_message)],
        "sender": sender_name,
        "vulns": state["vulns"],
        "check_count": check_count,
    }


@dataclass(slots=True)
class NodeSet:
    scan: StateHandler
    inquire: StateHandler
    exploit: StateHandler
    vuln_select: StateHandler
    check: StateHandler


def build_nodes(
    *,
    llm: "BaseChatModel",
    prompts: PromptBundle,
    tool_specs: list[ToolSpec],
    context: WorkflowContext,
) -> NodeSet:
    try:
        from langchain.agents import create_react_agent
        from langchain_core.prompts import PromptTemplate
    except ImportError as exc:
        raise RuntimeError(
            "LangChain is required to build workflow nodes."
        ) from exc

    scan_tools = build_langchain_tools([tool for tool in tool_specs if tool.name == "EXECMD"])
    inquire_tools = build_langchain_tools([tool for tool in tool_specs if tool.name == "ReadHTML"])
    exploit_tools = build_langchain_tools([tool for tool in tool_specs if tool.name == "EXECMD"])

    scan_agent = create_react_agent(
        llm=llm,
        tools=scan_tools,
        prompt=PromptTemplate.from_template(prompts.scan),
    )
    inquire_agent = create_react_agent(
        llm=llm,
        tools=inquire_tools,
        prompt=PromptTemplate.from_template(prompts.inquire),
    )
    exploit_agent = create_react_agent(
        llm=llm,
        tools=exploit_tools,
        prompt=PromptTemplate.from_template(prompts.exploit),
    )

    return NodeSet(
        scan=partial(agent_node, context=context, agent=scan_agent, tools=scan_tools, sender_name="Scan"),
        inquire=partial(agent_node, context=context, agent=inquire_agent, tools=inquire_tools, sender_name="Inquire"),
        exploit=partial(agent_node, context=context, agent=exploit_agent, tools=exploit_tools, sender_name="Exploit"),
        vuln_select=partial(vuln_select_node, context=context, sender_name="Vuln_select"),
        check=partial(check_node, context=context, sender_name="Check"),
    )

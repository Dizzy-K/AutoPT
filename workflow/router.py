from __future__ import annotations

"""Conditional routing logic for the workflow state graph."""

from .parser import message_content
from .state import WorkflowState


def route_next(state: WorkflowState) -> str:
    messages = state["message"]
    sender = state["sender"]
    last_message = message_content(messages[-1]) if messages else ""

    if sender == "Scan":
        return "Vuln_select"
    if sender == "Vuln_select":
        return "Inquire"
    if sender == "Inquire":
        return "Exploit"
    if sender == "Exploit":
        return "Check"
    if sender == "Check":
        if "Successfully exploited the vulnerability" in last_message:
            return "__end__"
        if "please try again." in last_message:
            return "Exploit"
        if "please try another vulnerability." in last_message:
            return "Vuln_select"
        if "Failed to exploit the vulnerability." in last_message:
            return "__end__"
        return "__end__"
    return "__end__"

"""Workflow state, routing, parsing, and builder interfaces.

This package models the LangGraph-based agent workflow used by AutoPT:
scan -> vuln_select -> inquire -> exploit -> check, with conditional routing.
"""

# Core workflow types: definition model and builder function.
from .builder import WorkflowDefinition, build_workflow_definition
from .state import WorkflowContext, WorkflowState

__all__ = ["WorkflowContext", "WorkflowDefinition", "WorkflowState", "build_workflow_definition"]

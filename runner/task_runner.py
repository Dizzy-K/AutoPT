from __future__ import annotations

"""Single-task execution engine and request/result data types."""

import asyncio
from dataclasses import dataclass, field
from time import time
from typing import Any

from autopt.benchmark.models import BenchmarkItem
from autopt.config.schema import AppConfig
from autopt.models.providers import build_chat_model
from autopt.models.registry import ModelSpec
from autopt.prompts.registry import get_prompt_bundle
from autopt.prompts.templates import PromptBundle
from autopt.tools.registry import build_default_tool_specs
from autopt.workflow import WorkflowContext, build_workflow_definition
from autopt.workflow.builder import WorkflowDefinition

from .result_schema import build_task_result_details, serialize_json_value, serialize_task_result


@dataclass(slots=True)
class TaskRequest:
    benchmark: BenchmarkItem
    model: ModelSpec
    ip_addr: str
    prompts: PromptBundle
    workflow: WorkflowDefinition
    prompt_bundle_name: str = "default"
    config: AppConfig = field(default_factory=AppConfig)


@dataclass(slots=True)
class TaskResult:
    status: str
    runtime: float
    benchmark_name: str
    model_alias: str
    ip_addr: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return serialize_task_result(self)


def build_task_request(
    *,
    benchmark: BenchmarkItem,
    model: ModelSpec,
    ip_addr: str,
    config: AppConfig | None = None,
    prompt_bundle_name: str = "default",
    prompts: PromptBundle | None = None,
) -> TaskRequest:
    app_config = config or AppConfig()
    prompt_bundle = prompts or get_prompt_bundle(prompt_bundle_name, benchmark=benchmark)
    tool_specs = build_default_tool_specs(runtime_config=app_config.runtime, tools_config=app_config.tools)
    context = WorkflowContext(
        benchmark_name=benchmark.name,
        config=app_config,
        benchmark=benchmark,
    )
    context.bind_target(ip_addr, benchmark.target)
    workflow = build_workflow_definition(
        context=context,
        prompts=prompt_bundle,
        tool_specs=tool_specs,
        metadata={"benchmark_name": benchmark.name, "model_alias": model.alias},
    )
    return TaskRequest(
        benchmark=benchmark,
        model=model,
        ip_addr=ip_addr,
        prompts=prompt_bundle,
        workflow=workflow,
        prompt_bundle_name=prompt_bundle_name,
        config=app_config,
    )


class TaskRunner:
    def run(self, request: TaskRequest) -> TaskResult:
        start = time()
        context = request.workflow.context
        context.history.clear()
        context.commands.clear()
        context.problem = context.problem_template
        context.bind_target(request.ip_addr, request.benchmark.target)

        try:
            llm = build_chat_model(request.model, request.config)
            graph = request.workflow.compile(llm)
            state = context.initial_state()
            result = self._invoke_graph(
                graph,
                state,
                recursion_limit=context.recursion_limit(),
            )
            runtime = time() - start
            status = self._status_from_history(context.history)
            return TaskResult(
                status=status,
                runtime=runtime,
                benchmark_name=request.benchmark.name,
                model_alias=request.model.alias,
                ip_addr=request.ip_addr,
                details=build_task_result_details(
                    target=request.benchmark.target,
                    benchmark=request.benchmark.to_dict(),
                    model=request.model.to_dict(),
                    architecture="FSM",
                    workflow_name="autopt.workflow.v1",
                    prompt_bundle_name=request.prompt_bundle_name,
                    result=serialize_json_value(result),
                    history=context.history,
                    commands=context.commands,
                    prompts=request.prompts.to_dict(),
                    workflow_edges=request.workflow.edges,
                ),
            )
        except Exception as exc:
            runtime = time() - start
            return TaskResult(
                status="error",
                runtime=runtime,
                benchmark_name=request.benchmark.name,
                model_alias=request.model.alias,
                ip_addr=request.ip_addr,
                details=build_task_result_details(
                    target=request.benchmark.target,
                    benchmark=request.benchmark.to_dict(),
                    model=request.model.to_dict(),
                    architecture="FSM",
                    workflow_name="autopt.workflow.v1",
                    prompt_bundle_name=request.prompt_bundle_name,
                    error=str(exc),
                    history=context.history,
                    commands=context.commands,
                    prompts=request.prompts.to_dict(),
                    workflow_edges=request.workflow.edges,
                ),
            )

    @staticmethod
    def _status_from_history(history: list[str]) -> str:
        if history and "Successfully exploited the vulnerability" in history[-1]:
            return "success"
        return "failed"

    def _invoke_graph(self, graph: Any, state: Any, recursion_limit: int) -> Any:
        try:
            import nest_asyncio

            nest_asyncio.apply()
        except ImportError:
            pass

        coro = graph.ainvoke(state, config={"recursion_limit": recursion_limit})
        try:
            return asyncio.run(coro)
        except RuntimeError as exc:
            if "asyncio.run() cannot be called from a running event loop" not in str(exc):
                raise
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(coro)

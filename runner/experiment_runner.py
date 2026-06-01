from __future__ import annotations

"""Batch experiment runner executing task combinations and producing reports."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autopt.benchmark.loader import find_benchmark_by_name, load_benchmarks
from autopt.benchmark.models import BenchmarkItem
from autopt.config.schema import AppConfig
from autopt.models.registry import resolve_model

from .result_schema import build_experiment_report, summarize_task_results
from .result_writer import write_jsonl_record
from .task_runner import TaskRequest, TaskResult, TaskRunner, build_task_request


@dataclass(slots=True)
class ExperimentRequest:
    benchmark_file: str | Path
    benchmark_names: list[str] = field(default_factory=list)
    model_identifiers: list[str] = field(default_factory=list)
    ip_addr: str = ""
    repeat: int = 1
    config: AppConfig = field(default_factory=AppConfig)
    output_file: str | Path | None = None
    prompt_bundle_name: str = "default"


@dataclass(slots=True)
class ExperimentReport:
    benchmark_file: str
    output_file: str | None
    repeat: int
    benchmarks: list[str] = field(default_factory=list)
    models: list[str] = field(default_factory=list)
    results: list[TaskResult] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return summarize_task_results(self.results)

    def to_dict(self) -> dict[str, Any]:
        return build_experiment_report(
            benchmark_file=self.benchmark_file,
            output_file=self.output_file,
            repeat=self.repeat,
            benchmarks=self.benchmarks,
            models=self.models,
            results=self.results,
        )


@dataclass(slots=True)
class ExperimentRunner:
    """Orchestrate batch experiments across benchmarks x models x repeats."""
    task_runner: TaskRunner = field(default_factory=TaskRunner)

    def build_task_requests(self, request: ExperimentRequest) -> list[TaskRequest]:
        benchmarks = self._resolve_benchmarks(request.benchmark_file, request.benchmark_names)
        if not request.model_identifiers:
            raise ValueError("ExperimentRequest requires at least one model identifier.")

        task_requests: list[TaskRequest] = []
        for benchmark in benchmarks:
            for model_identifier in request.model_identifiers:
                task_requests.append(
                    build_task_request(
                        benchmark=benchmark,
                        model=resolve_model(
                            model_identifier,
                            default_provider=request.config.llm.default_provider,
                        ),
                        ip_addr=request.ip_addr,
                        config=request.config,
                        prompt_bundle_name=request.prompt_bundle_name,
                    )
                )
        return task_requests

    def run(self, request: ExperimentRequest) -> ExperimentReport:
        results: list[TaskResult] = []
        task_requests = self.build_task_requests(request)
        benchmarks = self._dedupe_names(task_request.benchmark.name for task_request in task_requests)
        total_rounds = max(request.repeat, 1)
        report = ExperimentReport(
            benchmark_file=str(request.benchmark_file),
            output_file=str(request.output_file) if request.output_file else None,
            repeat=total_rounds,
            benchmarks=benchmarks,
            models=list(request.model_identifiers),
        )

        for round_index in range(total_rounds):
            for task_request in task_requests:
                result = self.task_runner.run(task_request)
                result.details["round_index"] = round_index
                results.append(result)
                if request.output_file:
                    write_jsonl_record(request.output_file, result.to_dict())
        report.results.extend(results)
        return report

    @staticmethod
    def _resolve_benchmarks(benchmark_file: str | Path, benchmark_names: list[str]) -> list[BenchmarkItem]:
        if benchmark_names:
            return [find_benchmark_by_name(benchmark_file, name) for name in benchmark_names]
        return load_benchmarks(benchmark_file)

    @staticmethod
    def _dedupe_names(names: Any) -> list[str]:
        deduped: list[str] = []
        for name in names:
            value = str(name)
            if value not in deduped:
                deduped.append(value)
        return deduped

    @staticmethod
    def summarize(results: list[TaskResult]) -> dict[str, Any]:
        return summarize_task_results(results)

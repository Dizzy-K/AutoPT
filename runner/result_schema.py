from __future__ import annotations

"""Task and experiment result serialization schemas and helpers."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


# Schema version constants for task and experiment report payloads.
TASK_RESULT_SCHEMA_VERSION = "autopt.task_result.v1"
EXPERIMENT_REPORT_SCHEMA_VERSION = "autopt.experiment_report.v1"


def serialize_json_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Mapping):
        return {str(key): serialize_json_value(val) for key, val in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [serialize_json_value(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return serialize_json_value(value.to_dict())
    if hasattr(value, "content"):
        return serialize_json_value(value.content)
    return str(value)


def _serialize_mapping(value: Any) -> dict[str, Any]:
    serialized = serialize_json_value(value)
    if isinstance(serialized, dict):
        return serialized
    return {}


def _serialize_list(value: Any) -> list[Any]:
    serialized = serialize_json_value(value)
    if isinstance(serialized, list):
        return serialized
    return []


def build_task_result_details(
    *,
    target: str,
    benchmark: Mapping[str, Any] | None = None,
    model: Mapping[str, Any] | None = None,
    architecture: str = "",
    workflow_name: str = "",
    prompt_bundle_name: str = "",
    history: Sequence[Any] | None = None,
    commands: Sequence[Any] | None = None,
    prompts: Mapping[str, Any] | None = None,
    workflow_edges: Sequence[Any] | None = None,
    result: Any = None,
    error: str | None = None,
    round_index: int | None = None,
    extras: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    model_payload = dict(model or {})
    payload: dict[str, Any] = {
        "target": target,
        "benchmark": dict(benchmark or {}),
        "model": model_payload,
        "model_name": model_payload.get("name", ""),
        "provider": model_payload.get("provider", ""),
        "architecture": architecture,
        "workflow_name": workflow_name,
        "prompt_bundle_name": prompt_bundle_name,
        "round_index": round_index,
        "history": list(history or []),
        "commands": list(commands or []),
        "prompts": dict(prompts or {}),
        "workflow_edges": list(workflow_edges or []),
        "result": result,
        "error": error,
    }
    if extras:
        payload.update(dict(extras))
    return normalize_task_details(payload)


def normalize_task_details(details: Mapping[str, Any] | None) -> dict[str, Any]:
    source = dict(details or {})
    error = source.pop("error", None)
    round_index = source.pop("round_index", None)
    normalized: dict[str, Any] = {
        "target": str(source.pop("target", "")),
        "benchmark": _serialize_mapping(source.pop("benchmark", {})),
        "model": _serialize_mapping(source.pop("model", {})),
        "model_name": str(source.pop("model_name", "")),
        "provider": str(source.pop("provider", "")),
        "architecture": str(source.pop("architecture", "")),
        "workflow_name": str(source.pop("workflow_name", "")),
        "prompt_bundle_name": str(source.pop("prompt_bundle_name", "")),
        "round_index": int(round_index) if isinstance(round_index, int) else None,
        "history": _serialize_list(source.pop("history", [])),
        "commands": _serialize_list(source.pop("commands", [])),
        "prompts": _serialize_mapping(source.pop("prompts", {})),
        "workflow_edges": _serialize_list(source.pop("workflow_edges", [])),
        "result": serialize_json_value(source.pop("result", None)),
        "error": None if error is None else str(error),
    }
    extras = _serialize_mapping(source)
    if extras:
        normalized["extras"] = extras
    return normalized


def serialize_task_result(result: Any) -> dict[str, Any]:
    return {
        "schema_version": TASK_RESULT_SCHEMA_VERSION,
        "status": str(getattr(result, "status", "")),
        "runtime": float(getattr(result, "runtime", 0.0)),
        "benchmark_name": str(getattr(result, "benchmark_name", "")),
        "model_alias": str(getattr(result, "model_alias", "")),
        "ip_addr": str(getattr(result, "ip_addr", "")),
        "details": normalize_task_details(getattr(result, "details", {})),
    }


def summarize_task_results(results: Sequence[Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "total": len(results),
        "success": 0,
        "failed": 0,
        "error": 0,
    }
    for result in results:
        status = str(getattr(result, "status", ""))
        if status not in summary:
            summary[status] = 0
        summary[status] += 1
    return summary


def _status_from_summary(summary: Mapping[str, Any]) -> str:
    total = int(summary.get("total", 0) or 0)
    error_count = int(summary.get("error", 0) or 0)
    if total == 0:
        return "empty"
    if error_count == 0:
        return "ok"
    if error_count == total:
        return "error"
    return "partial_error"


def build_experiment_report(
    *,
    benchmark_file: str | Path,
    output_file: str | Path | None,
    repeat: int,
    benchmarks: Sequence[str],
    models: Sequence[str],
    results: Sequence[Any],
) -> dict[str, Any]:
    summary = summarize_task_results(results)
    return {
        "schema_version": EXPERIMENT_REPORT_SCHEMA_VERSION,
        "status": _status_from_summary(summary),
        "benchmark_file": str(benchmark_file),
        "output_file": str(output_file) if output_file else None,
        "repeat": int(repeat),
        "benchmarks": [str(item) for item in benchmarks],
        "models": [str(item) for item in models],
        "summary": summary,
        "results": [serialize_task_result(result) for result in results],
    }

from __future__ import annotations

"""Metric summarization and aggregation for normalized benchmark results.

This module supports grouping by single or composite fields,
solve-rate bucketing, and export of summary rows for downstream reporting.
"""

"""Metric summarization and aggregation for normalized benchmark results.

This module supports grouping by single or composite fields,
solve-rate bucketing, and export of summary rows for downstream reporting.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .loader import NormalizedResult


_SIMPLE_FIELD_GETTERS = {
    "benchmark": lambda item: item.benchmark_name,
    "benchmark_name": lambda item: item.benchmark_name,
    "model": lambda item: item.model_alias,
    "model_alias": lambda item: item.model_alias,
    "arch": lambda item: item.arch,
    "workflow_name": lambda item: item.workflow_name,
    "prompt_bundle_name": lambda item: item.prompt_bundle_name,
    "difficulty": lambda item: item.difficulty,
    "category": lambda item: item.category,
    "status": lambda item: item.status,
    "source_dir": lambda item: Path(item.source_dir).name if item.source_dir else "",
    "source_file": lambda item: item.source_file,
}

_COMPOSITE_FIELDS = {
    "model_arch": ("model", "arch"),
    "model_benchmark": ("model", "benchmark"),
    "model_arch_difficulty": ("model", "arch", "difficulty"),
}


def summarize_results(results: Iterable[NormalizedResult]) -> dict[str, Any]:
    result_list = list(results)
    tables = {
        "benchmark": summarize_by_field(result_list, "benchmark"),
        "model": summarize_by_field(result_list, "model"),
        "arch": summarize_by_field(result_list, "arch"),
        "difficulty": summarize_by_field(result_list, "difficulty"),
        "category": summarize_by_field(result_list, "category"),
        "model_arch": summarize_by_field(result_list, "model_arch"),
        "model_benchmark": summarize_by_field(result_list, "model_benchmark"),
        "model_arch_difficulty": summarize_by_field(result_list, "model_arch_difficulty"),
        "benchmark_solve_model_arch_difficulty": summarize_solve_rate(
            result_list,
            bucket_field="model_arch_difficulty",
        ),
    }
    return {
        "total": len(result_list),
        "status_counts": _status_counts(result_list),
        "success_rate": _success_rate(result_list),
        "total_runtime": _total_runtime(result_list),
        "average_runtime": _average_runtime(result_list),
        "tables": tables,
    }


def summarize_by_field(results: Iterable[NormalizedResult], field: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[NormalizedResult]] = defaultdict(list)
    for item in results:
        grouped[group_key(item, field)].append(item)

    output: dict[str, dict[str, Any]] = {}
    for name, items in sorted(grouped.items()):
        output[name] = _bucket_metrics(items)
    return output


def summarize_solve_rate(
    results: Iterable[NormalizedResult],
    *,
    bucket_field: str,
) -> dict[str, dict[str, Any]]:
    grouped_runs: dict[str, dict[str, list[NormalizedResult]]] = defaultdict(lambda: defaultdict(list))
    for item in results:
        benchmark_name = group_key(item, "benchmark")
        grouped_runs[group_key(item, bucket_field)][benchmark_name].append(item)

    output: dict[str, dict[str, Any]] = {}
    for bucket_name, benchmark_groups in sorted(grouped_runs.items()):
        solved = 0
        attempts_total = 0
        k_values: list[int] = []
        for runs in benchmark_groups.values():
            attempts_total += len(runs)
            k_values.append(len(runs))
            if any(run.status == "success" for run in runs):
                solved += 1
        total = len(benchmark_groups)
        output[bucket_name] = {
            "total": total,
            "success": solved,
            "failed": total - solved,
            "error": 0,
            "other": 0,
            "success_rate": (solved / total) if total else 0.0,
            "average_runtime": _average_runtime(
                run for runs in benchmark_groups.values() for run in runs
            ),
            "total_runtime": _total_runtime(run for runs in benchmark_groups.values() for run in runs),
            "attempt_total": attempts_total,
            "k_min": min(k_values) if k_values else 0,
            "k_max": max(k_values) if k_values else 0,
        }
    return output


def export_summary_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for category, table in summary.get("tables", {}).items():
        if not isinstance(table, dict):
            continue
        for name, metrics in table.items():
            if not isinstance(metrics, dict):
                continue
            row = {
                "Category": category,
                "Name": name,
                "Count": metrics.get("total", 0),
                "Failed": metrics.get("failed", 0),
                "Success": metrics.get("success", 0),
                "Error": metrics.get("error", 0),
                "Other": metrics.get("other", 0),
                "Ratio": f"{float(metrics.get('success_rate', 0.0)):.2%}",
                "TotalRuntime": metrics.get("total_runtime"),
                "AverageRuntime": metrics.get("average_runtime"),
            }
            if "attempt_total" in metrics:
                row["AttemptTotal"] = metrics["attempt_total"]
            if "k_min" in metrics:
                row["KMin"] = metrics["k_min"]
            if "k_max" in metrics:
                row["KMax"] = metrics["k_max"]
            rows.append(row)
    return rows


def build_metric_matrix(
    results: Iterable[NormalizedResult],
    *,
    rows_field: str,
    cols_field: str,
    metric: str = "success_rate",
) -> dict[str, Any]:
    result_list = list(results)
    row_names = sorted({group_key(item, rows_field) for item in result_list})
    col_names = sorted({group_key(item, cols_field) for item in result_list})
    matrix: dict[str, dict[str, float | int | None]] = {}
    for row_name in row_names:
        matrix[row_name] = {}
        for col_name in col_names:
            cell_items = [
                item
                for item in result_list
                if group_key(item, rows_field) == row_name and group_key(item, cols_field) == col_name
            ]
            matrix[row_name][col_name] = metric_value(cell_items, metric)
    return {
        "rows": row_names,
        "cols": col_names,
        "metric": metric,
        "values": matrix,
    }


def metric_value(results: Iterable[NormalizedResult], metric: str) -> float | int | None:
    result_list = list(results)
    if metric == "count":
        return len(result_list)
    if metric == "success_count":
        return sum(1 for item in result_list if item.status == "success")
    if metric == "failed_count":
        return sum(1 for item in result_list if item.status == "failed")
    if metric == "total_runtime":
        return _total_runtime(result_list)
    if metric == "average_runtime":
        return _average_runtime(result_list)
    if metric == "success_rate":
        return _success_rate(result_list)
    raise ValueError(f"Unsupported metric: {metric}")


def group_key(item: NormalizedResult, field: str) -> str:
    if field in _COMPOSITE_FIELDS:
        return "::".join(group_key(item, part) for part in _COMPOSITE_FIELDS[field])
    getter = _SIMPLE_FIELD_GETTERS.get(field)
    if getter is None:
        raise ValueError(f"Unsupported group field: {field}")
    value = str(getter(item) or "").strip()
    return value or "UNKNOWN"


def available_group_fields() -> list[str]:
    return sorted(set(_SIMPLE_FIELD_GETTERS) | set(_COMPOSITE_FIELDS))


def _bucket_metrics(results: Iterable[NormalizedResult]) -> dict[str, Any]:
    result_list = list(results)
    counts = _status_counts(result_list)
    success = counts.get("success", 0)
    failed = counts.get("failed", 0)
    error = counts.get("error", 0)
    other = len(result_list) - success - failed - error
    return {
        "total": len(result_list),
        "success": success,
        "failed": failed,
        "error": error,
        "other": other,
        "status_counts": counts,
        "success_rate": _success_rate(result_list),
        "total_runtime": _total_runtime(result_list),
        "average_runtime": _average_runtime(result_list),
    }


def _status_counts(results: Iterable[NormalizedResult]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for item in results:
        counts[item.status or "UNKNOWN"] += 1
    return dict(sorted(counts.items()))


def _success_rate(results: Iterable[NormalizedResult]) -> float:
    result_list = list(results)
    if not result_list:
        return 0.0
    success = sum(1 for item in result_list if item.status == "success")
    return success / len(result_list)


def _average_runtime(results: Iterable[NormalizedResult]) -> float | None:
    runtimes = [item.runtime for item in results if item.runtime is not None]
    if not runtimes:
        return None
    return sum(runtimes) / len(runtimes)


def _total_runtime(results: Iterable[NormalizedResult]) -> float:
    return sum(item.runtime for item in results if item.runtime is not None)

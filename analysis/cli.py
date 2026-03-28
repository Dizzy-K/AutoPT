from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Sequence

from .failures import collect_failed_commands, summarize_failure_reasons
from .history import group_history_steps, parse_history_entries
from .loader import NormalizedResult, load_normalized_results
from .plotting import render_grouped_bar_chart
from .summary import (
    available_group_fields,
    build_metric_matrix,
    export_summary_rows,
    summarize_results,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified Auto_RT result analysis entrypoint.")
    configure_analysis_subcommands(parser)
    return parser


def configure_analysis_subcommands(parser: argparse.ArgumentParser) -> None:
    subparsers = parser.add_subparsers(dest="analysis_command", required=True)

    summary_parser = subparsers.add_parser("summary", help="Summarize result JSONL files.")
    _add_input_arguments(summary_parser)
    _add_filter_arguments(summary_parser)
    summary_parser.add_argument("--output", default=None, help="Optional JSON output path.")

    csv_parser = subparsers.add_parser("export-csv", help="Export flattened summary rows to CSV.")
    _add_input_arguments(csv_parser)
    _add_filter_arguments(csv_parser)
    csv_parser.add_argument("--output", required=True, help="CSV output path.")

    matrix_parser = subparsers.add_parser("matrix", help="Build a grouped metric matrix.")
    _add_input_arguments(matrix_parser)
    _add_filter_arguments(matrix_parser)
    matrix_parser.add_argument("--rows", default="benchmark", choices=available_group_fields())
    matrix_parser.add_argument("--cols", default="model", choices=available_group_fields())
    matrix_parser.add_argument(
        "--metric",
        default="success_rate",
        choices=["success_rate", "count", "success_count", "failed_count", "total_runtime", "average_runtime"],
    )
    matrix_parser.add_argument("--output", default=None, help="Optional CSV or JSON output path.")

    history_parser = subparsers.add_parser("history", help="Print histories from matching records.")
    _add_input_arguments(history_parser)
    _add_filter_arguments(history_parser)
    history_parser.add_argument("--parsed", action="store_true", help="Parse workflow history entries.")

    fail_command_parser = subparsers.add_parser(
        "fail-commands",
        help="Collect commands from failed records grouped by the selected field.",
    )
    _add_input_arguments(fail_command_parser)
    _add_filter_arguments(fail_command_parser)
    fail_command_parser.add_argument("--group-by", default="model_arch", choices=available_group_fields())

    fail_reason_parser = subparsers.add_parser(
        "fail-reasons",
        help="Summarize failure reasons grouped by the selected field.",
    )
    _add_input_arguments(fail_reason_parser)
    _add_filter_arguments(fail_reason_parser)
    fail_reason_parser.add_argument("--group-by", default="model_arch", choices=available_group_fields())

    plot_parser = subparsers.add_parser("plot", help="Render a grouped bar chart from result data.")
    _add_input_arguments(plot_parser)
    _add_filter_arguments(plot_parser)
    plot_parser.add_argument("--x", default="model", choices=available_group_fields())
    plot_parser.add_argument("--series", default="arch", choices=available_group_fields())
    plot_parser.add_argument(
        "--metric",
        default="success_rate",
        choices=["success_rate", "count", "success_count", "failed_count", "total_runtime", "average_runtime"],
    )
    plot_parser.add_argument("--output", required=True, help="Plot output path, such as chart.png.")
    plot_parser.add_argument("--title", default=None, help="Optional chart title.")
    plot_parser.add_argument("--ylabel", default=None, help="Optional y-axis label.")


def handle_analysis_command(args: argparse.Namespace) -> int:
    results = _filtered_results(args)

    if args.analysis_command == "summary":
        payload = summarize_results(results)
        return _emit_json(payload, args.output)

    if args.analysis_command == "export-csv":
        payload = summarize_results(results)
        rows = export_summary_rows(payload)
        _write_csv(Path(args.output), rows)
        return 0

    if args.analysis_command == "matrix":
        payload = build_metric_matrix(
            results,
            rows_field=args.rows,
            cols_field=args.cols,
            metric=args.metric,
        )
        if args.output:
            output_path = Path(args.output)
            if output_path.suffix.lower() == ".csv":
                _write_matrix_csv(output_path, args.rows, payload)
                return 0
            return _emit_json(payload, output_path)
        return _emit_json(payload, None)

    if args.analysis_command == "history":
        payload: list[dict[str, Any]] = []
        for item in results:
            record = item.to_dict()
            if args.parsed:
                record["history_parsed"] = parse_history_entries(item.history)
                record["history_steps"] = group_history_steps(item.history)
            payload.append(record)
        return _emit_json(payload, None)

    if args.analysis_command == "fail-commands":
        payload = collect_failed_commands(results, group_by=args.group_by)
        return _emit_json(payload, None)

    if args.analysis_command == "fail-reasons":
        payload = summarize_failure_reasons(results, group_by=args.group_by)
        return _emit_json(payload, None)

    if args.analysis_command == "plot":
        matrix = build_metric_matrix(
            results,
            rows_field=args.x,
            cols_field=args.series,
            metric=args.metric,
        )
        try:
            render_grouped_bar_chart(
                matrix,
                output_path=args.output,
                title=args.title,
                ylabel=args.ylabel,
            )
        except RuntimeError as exc:
            print(str(exc))
            return 1
        return 0

    raise ValueError(f"Unsupported analysis command: {args.analysis_command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return handle_analysis_command(args)


def _filtered_results(args: argparse.Namespace) -> list[NormalizedResult]:
    results = load_normalized_results(args.inputs, benchmark_files=getattr(args, "benchmark_file", None) or [])
    filtered: list[NormalizedResult] = []
    for item in results:
        if getattr(args, "benchmark_name", None) and item.benchmark_name != args.benchmark_name:
            continue
        if getattr(args, "model", None) and item.model_alias != args.model:
            continue
        if getattr(args, "arch", None) and item.arch != args.arch:
            continue
        if getattr(args, "status", None) and item.status != args.status:
            continue
        if getattr(args, "difficulty", None) and item.difficulty != args.difficulty:
            continue
        if getattr(args, "category", None) and item.category != args.category:
            continue
        if getattr(args, "workflow_name", None) and item.workflow_name != args.workflow_name:
            continue
        if getattr(args, "prompt_bundle_name", None) and item.prompt_bundle_name != args.prompt_bundle_name:
            continue
        filtered.append(item)
    return filtered


def _add_input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("inputs", nargs="+", help="JSONL file(s) or directories containing JSONL files.")
    parser.add_argument(
        "--benchmark-file",
        action="append",
        default=[],
        help="Optional benchmark JSONL file for metadata enrichment. Can be passed multiple times.",
    )


def _add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--benchmark-name", default=None, help="Filter by benchmark name.")
    parser.add_argument("--model", default=None, help="Filter by model alias.")
    parser.add_argument("--arch", default=None, help="Filter by architecture label.")
    parser.add_argument("--status", default=None, help="Filter by status.")
    parser.add_argument("--difficulty", default=None, help="Filter by benchmark difficulty.")
    parser.add_argument("--category", default=None, help="Filter by benchmark category.")
    parser.add_argument("--workflow-name", default=None, help="Filter by workflow name.")
    parser.add_argument("--prompt-bundle-name", default=None, help="Filter by prompt bundle name.")


def _emit_json(payload: Any, output: str | Path | None) -> int:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if output:
        Path(output).write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_matrix_csv(path: Path, row_label: str, matrix: dict[str, Any]) -> None:
    columns = [row_label] + list(matrix.get("cols", []))
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for row_name in matrix.get("rows", []):
            row = {row_label: row_name}
            row.update(matrix.get("values", {}).get(row_name, {}))
            writer.writerow(row)

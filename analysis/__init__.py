"""Unified result analysis helpers."""

from .failures import classify_failure, collect_failed_commands, summarize_failure_reasons
from .history import group_history_steps, parse_history_entries
from .loader import NormalizedResult, iter_normalized_results, load_normalized_results
from .summary import available_group_fields, build_metric_matrix, export_summary_rows, summarize_results

__all__ = [
    "NormalizedResult",
    "available_group_fields",
    "build_metric_matrix",
    "classify_failure",
    "collect_failed_commands",
    "export_summary_rows",
    "group_history_steps",
    "iter_normalized_results",
    "load_normalized_results",
    "parse_history_entries",
    "summarize_failure_reasons",
    "summarize_results",
]

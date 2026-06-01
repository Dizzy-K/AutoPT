from __future__ import annotations

"""Visualization and plotting utilities for benchmark result analysis."""

from typing import Any


def render_grouped_bar_chart(
    matrix: dict[str, Any],
    *,
    output_path: str,
    title: str | None = None,
    ylabel: str | None = None,
) -> None:
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("matplotlib is required for plot generation.") from exc

    rows = list(matrix.get("rows", []))
    cols = list(matrix.get("cols", []))
    values = matrix.get("values", {})
    metric = str(matrix.get("metric", "value"))

    if not rows or not cols:
        raise ValueError("No data available for plotting.")

    x = np.arange(len(rows))
    width = 0.8 / max(len(cols), 1)

    fig, ax = plt.subplots(figsize=(max(6.0, len(rows) * 1.1), 3.6))
    for index, column in enumerate(cols):
        offsets = x + ((index - (len(cols) - 1) / 2) * width)
        series_values = [values.get(row, {}).get(column, 0) or 0 for row in rows]
        ax.bar(offsets, series_values, width, label=column)

    ax.set_xticks(x)
    ax.set_xticklabels(rows, rotation=20, ha="right")
    ax.set_ylabel(ylabel or metric.replace("_", " ").title())
    if title:
        ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(fig)

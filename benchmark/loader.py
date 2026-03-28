from __future__ import annotations

import json
from pathlib import Path

from .models import BenchmarkItem


def load_benchmarks(path: str | Path) -> list[BenchmarkItem]:
    benchmark_path = Path(path)
    items: list[BenchmarkItem] = []
    with benchmark_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            items.append(BenchmarkItem.from_dict(json.loads(line)))
    return items


def find_benchmark_by_name(path: str | Path, benchmark_name: str) -> BenchmarkItem:
    for item in load_benchmarks(path):
        if item.name == benchmark_name:
            return item
    raise ValueError(f"Benchmark `{benchmark_name}` not found in `{path}`.")

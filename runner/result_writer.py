from __future__ import annotations

"""JSONL result file writer with automatic directory creation."""

import json
from pathlib import Path
from typing import Any, Mapping


def write_jsonl_record(path: str | Path, payload: Mapping[str, Any]) -> None:
    """Append a JSON object as a single line to a JSONL file, creating parent directories as needed."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(dict(payload), ensure_ascii=False))
        stream.write("\n")

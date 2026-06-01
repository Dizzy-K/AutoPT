from __future__ import annotations

"""History entry parsing and step grouping for workflow transcripts."""

import re
from typing import Any, Iterable


_HISTORY_HEAD_PATTERN = re.compile(r"^(?P<sender>[A-Za-z_]+?)(?P<step>\d+)$")


def parse_history_entries(history: Iterable[Any]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for raw_entry in history:
        text = str(raw_entry)
        if "_response_" in text:
            head, content = text.split("_response_", 1)
            entry_type = "response"
        elif "_" in text:
            head, content = text.split("_", 1)
            entry_type = "message"
        else:
            parsed.append(
                {
                    "type": "plain",
                    "sender": "",
                    "step": None,
                    "content": text,
                    "raw": text,
                }
            )
            continue

        match = _HISTORY_HEAD_PATTERN.match(head)
        if not match:
            parsed.append(
                {
                    "type": "plain",
                    "sender": "",
                    "step": None,
                    "content": text,
                    "raw": text,
                }
            )
            continue

        sender = match.group("sender")
        step = int(match.group("step"))
        parsed.append(
            {
                "type": entry_type,
                "sender": sender,
                "step": step,
                "content": content,
                "raw": text,
            }
        )
    return parsed


def group_history_steps(history: Iterable[Any]) -> list[dict[str, Any]]:
    grouped: list[dict[str, Any]] = []
    positions: dict[tuple[str, int | None], int] = {}

    for entry in parse_history_entries(history):
        sender = str(entry.get("sender", ""))
        step = entry.get("step")
        entry_type = str(entry.get("type", "plain"))

        if not sender and entry_type == "plain":
            grouped.append(
                {
                    "sender": "",
                    "step": None,
                    "message": None,
                    "response": None,
                    "events": [entry],
                }
            )
            continue

        key = (sender, step)
        if key not in positions:
            positions[key] = len(grouped)
            grouped.append(
                {
                    "sender": sender,
                    "step": step,
                    "message": None,
                    "response": None,
                    "events": [],
                }
            )

        bucket = grouped[positions[key]]
        bucket["events"].append(entry)
        if entry_type == "message" and bucket["message"] is None:
            bucket["message"] = entry.get("content")
        elif entry_type == "response" and bucket["response"] is None:
            bucket["response"] = entry.get("content")

    return grouped

from __future__ import annotations

"""Data models for benchmark items and their metadata."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class BenchmarkItem:
    name: str
    target: str
    description: str = ""
    difficulty: str = ""
    references: list[str] = field(default_factory=list)
    category: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkItem":
        return cls(
            name=str(data.get("name", "")),
            target=str(data.get("target", "")),
            description=str(data.get("description", "")),
            difficulty=str(data.get("difficulty", "")),
            references=[str(item) for item in data.get("references", [])],
            category=str(data.get("type", data.get("category", ""))),
            raw=data,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "target": self.target,
            "description": self.description,
            "difficulty": self.difficulty,
            "references": self.references,
            "category": self.category,
        }

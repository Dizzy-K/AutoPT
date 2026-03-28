from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

from autort.benchmark.loader import load_benchmarks


_MODEL_ALIAS_ALIASES = {
    "4o": "gpt4o",
    "gpt-4o": "gpt4o",
    "gpt-4o-mini": "gpt4omini",
    "4omini": "gpt4omini",
    "gpt-3.5-turbo": "gpt35turbo",
    "gpt-3.5-turbo-0125": "gpt35turbo",
}


@dataclass(slots=True)
class NormalizedResult:
    status: str
    runtime: float | None
    benchmark_name: str
    model_alias: str
    arch: str = ""
    workflow_name: str = ""
    prompt_bundle_name: str = ""
    difficulty: str = ""
    category: str = ""
    benchmark_target: str = ""
    ip_addr: str = ""
    source_file: str = ""
    source_dir: str = ""
    target: str = ""
    run_index: int | None = None
    commands: list[Any] = field(default_factory=list)
    history: list[Any] = field(default_factory=list)
    prompts: dict[str, Any] = field(default_factory=dict)
    benchmark: dict[str, Any] = field(default_factory=dict)
    model: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "runtime": self.runtime,
            "benchmark_name": self.benchmark_name,
            "model_alias": self.model_alias,
            "arch": self.arch,
            "workflow_name": self.workflow_name,
            "prompt_bundle_name": self.prompt_bundle_name,
            "difficulty": self.difficulty,
            "category": self.category,
            "benchmark_target": self.benchmark_target,
            "ip_addr": self.ip_addr,
            "source_file": self.source_file,
            "source_dir": self.source_dir,
            "target": self.target,
            "run_index": self.run_index,
            "commands": self.commands,
            "history": self.history,
            "prompts": self.prompts,
            "benchmark": self.benchmark,
            "model": self.model,
            "raw": self.raw,
        }


def load_normalized_results(
    paths: str | Path | Sequence[str | Path],
    *,
    benchmark_files: Sequence[str | Path] | None = None,
) -> list[NormalizedResult]:
    return list(iter_normalized_results(paths, benchmark_files=benchmark_files))


def iter_normalized_results(
    paths: str | Path | Sequence[str | Path],
    *,
    benchmark_files: Sequence[str | Path] | None = None,
) -> Iterator[NormalizedResult]:
    benchmark_index = _load_benchmark_index(benchmark_files or [])
    for input_path in _coerce_input_paths(paths):
        for jsonl_path in _iter_jsonl_files(input_path):
            yield from _iter_jsonl_results(jsonl_path, benchmark_index)


def _coerce_input_paths(paths: str | Path | Sequence[str | Path]) -> list[Path]:
    if isinstance(paths, (str, Path)):
        return [Path(paths)]
    return [Path(item) for item in paths]


def _iter_jsonl_files(path: Path) -> Iterator[Path]:
    if path.is_file():
        if path.suffix.lower() == ".jsonl":
            yield path
        return
    if not path.exists():
        return
    for child in sorted(path.rglob("*.jsonl")):
        if child.is_file():
            yield child


def _iter_jsonl_results(path: Path, benchmark_index: dict[str, dict[str, Any]]) -> Iterator[NormalizedResult]:
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            yield from _normalize_payload(payload, path, benchmark_index)


def _normalize_payload(
    payload: dict[str, Any],
    source_path: Path,
    benchmark_index: dict[str, dict[str, Any]],
) -> Iterator[NormalizedResult]:
    schema_version = str(payload.get("schema_version", ""))
    if schema_version in {"autort.experiment_report.v1", "autort.legacy_main_compat.v1"}:
        for item in payload.get("results", []):
            if isinstance(item, dict):
                yield _normalize_task_result(item, source_path, benchmark_index)
        for report in payload.get("reports", []):
            if not isinstance(report, dict):
                continue
            for item in report.get("results", []):
                if isinstance(item, dict):
                    yield _normalize_task_result(item, source_path, benchmark_index)
        return

    if schema_version == "autort.task_result.v1" or {"status", "benchmark_name", "model_alias"}.issubset(payload):
        yield _normalize_task_result(payload, source_path, benchmark_index)
        return

    if "flag" in payload:
        yield _normalize_legacy_result(payload, source_path, benchmark_index)


def _normalize_task_result(
    payload: dict[str, Any],
    source_path: Path,
    benchmark_index: dict[str, dict[str, Any]],
) -> NormalizedResult:
    details = payload.get("details", {})
    if not isinstance(details, dict):
        details = {}

    benchmark_payload = _as_dict(details.get("benchmark"))
    benchmark_name = str(payload.get("benchmark_name") or benchmark_payload.get("name") or "")
    benchmark_metadata = _merge_benchmark_metadata(benchmark_name, benchmark_payload, benchmark_index)

    model_payload = _as_dict(details.get("model"))
    model_alias = _canonicalize_model_alias(
        payload.get("model_alias") or model_payload.get("alias") or model_payload.get("name")
    )

    return NormalizedResult(
        status=str(payload.get("status", "")),
        runtime=_float_or_none(payload.get("runtime")),
        benchmark_name=benchmark_name or str(benchmark_metadata.get("name", "")),
        model_alias=model_alias,
        arch=_infer_arch(details, source_path),
        workflow_name=str(details.get("workflow_name", "")),
        prompt_bundle_name=str(details.get("prompt_bundle_name", "")),
        difficulty=str(benchmark_metadata.get("difficulty", "")),
        category=str(benchmark_metadata.get("category", benchmark_metadata.get("type", ""))),
        benchmark_target=str(benchmark_metadata.get("target", "")),
        ip_addr=str(payload.get("ip_addr", "")),
        source_file=str(source_path),
        source_dir=str(source_path.parent),
        target=str(details.get("target") or benchmark_metadata.get("target", "")),
        run_index=_int_or_none(details.get("round_index")),
        commands=_as_list(details.get("commands")),
        history=_as_list(details.get("history")),
        prompts=_as_dict(details.get("prompts")),
        benchmark=benchmark_metadata,
        model=model_payload,
        raw=payload,
    )


def _normalize_legacy_result(
    payload: dict[str, Any],
    source_path: Path,
    benchmark_index: dict[str, dict[str, Any]],
) -> NormalizedResult:
    legacy_metadata = _infer_legacy_metadata(source_path, benchmark_index)
    benchmark_metadata = _merge_benchmark_metadata(
        legacy_metadata["benchmark_name"],
        {},
        benchmark_index,
    )
    status = str(payload.get("flag", ""))
    if status == "success":
        normalized_status = "success"
    elif status == "failed":
        normalized_status = "failed"
    else:
        normalized_status = status

    return NormalizedResult(
        status=normalized_status,
        runtime=_float_or_none(payload.get("runtime", payload.get("time"))),
        benchmark_name=legacy_metadata["benchmark_name"],
        model_alias=legacy_metadata["model_alias"],
        arch=legacy_metadata["arch"],
        workflow_name="",
        prompt_bundle_name="",
        difficulty=str(benchmark_metadata.get("difficulty", "")),
        category=str(benchmark_metadata.get("category", benchmark_metadata.get("type", ""))),
        benchmark_target=str(benchmark_metadata.get("target", "")),
        source_file=str(source_path),
        source_dir=str(source_path.parent),
        target=str(benchmark_metadata.get("target", "")),
        run_index=_int_or_none(payload.get("count")),
        commands=_as_list(payload.get("commands")),
        history=_as_list(payload.get("history")),
        prompts=_as_dict(payload.get("prompts")),
        benchmark=benchmark_metadata,
        raw=payload,
    )


def _load_benchmark_index(benchmark_files: Sequence[str | Path]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for benchmark_file in benchmark_files:
        benchmark_path = Path(benchmark_file)
        if not benchmark_path.exists():
            continue
        for item in load_benchmarks(benchmark_path):
            payload = item.to_dict()
            payload["name"] = item.name
            index[_benchmark_lookup_key(item.name)] = payload
    return index


def _merge_benchmark_metadata(
    benchmark_name: str,
    inline_benchmark: dict[str, Any],
    benchmark_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    merged = dict(benchmark_index.get(_benchmark_lookup_key(benchmark_name), {}))
    if inline_benchmark:
        merged.update(inline_benchmark)
    if benchmark_name and "name" not in merged:
        merged["name"] = benchmark_name
    return merged


def _infer_legacy_metadata(
    source_path: Path,
    benchmark_index: dict[str, dict[str, Any]],
) -> dict[str, str]:
    parts = source_path.stem.split("_")
    arch = parts[-1] if parts else ""
    model_alias = ""
    benchmark_tokens: list[str] = []

    if len(parts) >= 4:
        model_alias = _canonicalize_model_alias(parts[-2])
        benchmark_tokens = parts[:-2]
    elif len(parts) == 3:
        model_alias = _canonicalize_model_alias(source_path.parent.name or "gpt4omini")
        benchmark_tokens = parts[:-1]
    else:
        benchmark_tokens = parts[:-1] if len(parts) > 1 else parts

    if not model_alias:
        model_alias = _canonicalize_model_alias(source_path.parent.name)

    benchmark_name = _match_benchmark_name(benchmark_tokens, benchmark_index)
    if not benchmark_name:
        benchmark_name = _benchmark_name_from_tokens(benchmark_tokens)

    return {
        "benchmark_name": benchmark_name,
        "model_alias": model_alias,
        "arch": arch,
    }


def _match_benchmark_name(
    benchmark_tokens: Sequence[str],
    benchmark_index: dict[str, dict[str, Any]],
) -> str:
    if not benchmark_tokens or not benchmark_index:
        return ""

    joined = _benchmark_lookup_key("/".join(benchmark_tokens))
    best_name = ""
    best_length = 0
    for key, metadata in benchmark_index.items():
        if not key:
            continue
        if key == joined or key in joined or joined in key:
            name = str(metadata.get("name", ""))
            if len(key) > best_length:
                best_name = name
                best_length = len(key)
    return best_name


def _benchmark_name_from_tokens(tokens: Sequence[str]) -> str:
    if not tokens:
        return ""
    if len(tokens) == 1:
        return tokens[0]
    if len(tokens) == 2:
        return f"{tokens[0]}/{tokens[1]}"
    return f"{tokens[0]}/{'-'.join(tokens[1:])}"


def _benchmark_lookup_key(name: str) -> str:
    return "".join(character.lower() for character in name if character.isalnum())


def _infer_arch(details: dict[str, Any], source_path: Path) -> str:
    arch = str(
        details.get("architecture")
        or _as_dict(details.get("extras")).get("architecture")
        or _as_dict(details.get("extras")).get("arch")
        or ""
    )
    if arch:
        return arch

    stem_parts = source_path.stem.split("_")
    if len(stem_parts) >= 3:
        return stem_parts[-1]
    return ""


def _canonicalize_model_alias(value: Any) -> str:
    alias = str(value or "").strip()
    return _MODEL_ALIAS_ALIASES.get(alias, alias)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _float_or_none(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None

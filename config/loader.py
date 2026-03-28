from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .schema import (
    AppConfig,
    CommandToolProviderConfig,
    LLMConfig,
    LLMProviderConfig,
    OptimizationConfig,
    PathsConfig,
    RuntimeConfig,
    SSHConfig,
    ScannerToolConfig,
    TerminalToolConfig,
    ToolsConfig,
    WebToolConfig,
    WorkflowConfig,
)


class ConfigError(RuntimeError):
    """Raised when configuration loading fails."""


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise ConfigError("PyYAML is required to load YAML config files.") from exc

    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
        if not isinstance(data, dict):
            raise ConfigError(f"Config file must contain a mapping: {path}")
        return data


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _as_mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    return {}


def _merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        existing = merged.get(key)
        if isinstance(existing, Mapping) and isinstance(value, Mapping):
            merged[key] = _merge_dicts(existing, value)
        else:
            merged[key] = value
    return merged


def _coerce_path_list(value: Any, *, field_name: str) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [str(item) for item in value]
    raise ConfigError(f"`{field_name}` must be a string or list of strings.")


def _load_merged_yaml(path: Path, visited: set[Path] | None = None) -> dict[str, Any]:
    resolved_path = path.resolve()
    seen = visited or set()
    if resolved_path in seen:
        raise ConfigError(f"Config import cycle detected: {resolved_path}")
    seen.add(resolved_path)

    raw = _load_yaml_file(resolved_path)
    imports = _coerce_path_list(raw.pop("imports", []), field_name="imports")
    optional_imports = _coerce_path_list(raw.pop("optional_imports", []), field_name="optional_imports")

    merged: dict[str, Any] = {}
    for import_path in imports:
        child_path = (resolved_path.parent / import_path).resolve()
        if not child_path.exists():
            raise ConfigError(f"Imported config file does not exist: {child_path}")
        merged = _merge_dicts(merged, _load_merged_yaml(child_path, seen.copy()))

    merged = _merge_dicts(merged, raw)

    for import_path in optional_imports:
        child_path = (resolved_path.parent / import_path).resolve()
        if not child_path.exists():
            continue
        merged = _merge_dicts(merged, _load_merged_yaml(child_path, seen.copy()))

    return merged


def _build_workflow(data: Mapping[str, Any]) -> WorkflowConfig:
    return WorkflowConfig(
        sys_iterations=int(data.get("sys_iterations", 15)),
        exp_iterations=int(data.get("exp_iterations", 1)),
        query_iterations=int(data.get("query_iterations", 1)),
        scan_iterations=int(data.get("scan_iterations", 1)),
        debug=_coerce_bool(data.get("debug", False)),
        draw_graph=_coerce_bool(data.get("draw_graph", False)),
    )


def _build_llm_provider(data: Mapping[str, Any]) -> LLMProviderConfig:
    temperature = data.get("temperature")
    return LLMProviderConfig(
        api_base=str(data.get("api_base", data.get("openai_base", ""))),
        api_key=str(data.get("api_key", data.get("openai_key", ""))),
        temperature=float(temperature) if temperature not in (None, "") else None,
    )


def _build_llm(raw: Mapping[str, Any]) -> LLMConfig:
    llm_data = _as_mapping(raw.get("llm"))
    if llm_data:
        provider_payloads = {
            str(name): _build_llm_provider(_as_mapping(payload))
            for name, payload in _as_mapping(llm_data.get("providers")).items()
        }
        return LLMConfig(
            default_provider=str(llm_data.get("default_provider", "openai")),
            default_model=str(llm_data.get("default_model", "")),
            temperature=float(llm_data.get("temperature", 0.0)),
            providers=provider_payloads,
        )

    legacy_data = _as_mapping(raw.get("ai", raw.get("providers", {})))
    return LLMConfig(
        default_provider=str(legacy_data.get("default_provider", "openai")),
        default_model=str(legacy_data.get("default_model", raw.get("default_model", ""))),
        temperature=float(legacy_data.get("temperature", 0.0)),
        providers={
            "openai": LLMProviderConfig(
                api_base=str(legacy_data.get("openai_base", "")),
                api_key=str(legacy_data.get("openai_key", "")),
            ),
            "nvidia": LLMProviderConfig(
                api_key=str(legacy_data.get("nvidia_key", "")),
            ),
            "together": LLMProviderConfig(
                api_key=str(legacy_data.get("together_key", "")),
            ),
        },
    )


def _build_optimization(data: Mapping[str, Any]) -> OptimizationConfig:
    optimize_states = data.get("optimize_states", ["scan", "inquire", "exploit"])
    if not isinstance(optimize_states, list):
        raise ConfigError("`optimization.optimize_states` must be a list.")
    return OptimizationConfig(
        enabled=_coerce_bool(data.get("enabled", data.get("isopt", False))),
        model=str(data.get("model", "gpt-4")),
        optimize_states=[str(item) for item in optimize_states],
    )


def _build_ssh(data: Mapping[str, Any]) -> SSHConfig:
    return SSHConfig(
        host=str(data.get("host", "")),
        port=int(data.get("port", 22)),
        username=str(data.get("username", "root")),
        password=str(data.get("password", "")),
        timeout=int(data.get("timeout", 30)),
    )


def _build_runtime(raw: Mapping[str, Any]) -> RuntimeConfig:
    runtime_data = _as_mapping(raw.get("runtime"))
    ssh_data = _as_mapping(runtime_data.get("ssh", raw.get("ssh", {})))
    provider = str(runtime_data.get("provider", "local")).strip().lower() or "local"
    if provider not in {"local", "ssh"}:
        raise ConfigError("`runtime.provider` must be either `local` or `ssh`.")
    return RuntimeConfig(provider=provider, ssh=_build_ssh(ssh_data))


def _build_command_tool_provider(data: Mapping[str, Any], *, default_executable: str = "") -> CommandToolProviderConfig:
    return CommandToolProviderConfig(
        executable=str(data.get("executable", default_executable)),
        extra_args=[str(item) for item in data.get("extra_args", [])] if isinstance(data.get("extra_args", []), list) else [],
        env={str(key): str(value) for key, value in _as_mapping(data.get("env")).items()},
        working_directory=str(data.get("working_directory", "")),
    )


def _build_tools(raw: Mapping[str, Any]) -> ToolsConfig:
    tools_data = _as_mapping(raw.get("tools"))
    scanner_data = _as_mapping(tools_data.get("scanner"))
    scanner_runtime_data = scanner_data

    # Accept the old provider/providers layout for compatibility, but prefer
    # the flat scanner config in public-facing docs and templates.
    if "providers" in scanner_data or "provider" in scanner_data:
        scanner_provider_name = str(scanner_data.get("provider", "xray")).strip() or "xray"
        scanner_runtime_data = _as_mapping(_as_mapping(scanner_data.get("providers")).get(scanner_provider_name))
        if not scanner_runtime_data:
            scanner_runtime_data = scanner_data

    scanner_provider_config = _build_command_tool_provider(
        scanner_runtime_data,
        default_executable="xray",
    )

    return ToolsConfig(
        terminal=TerminalToolConfig(provider=str(_as_mapping(tools_data.get("terminal")).get("provider", "ssh"))),
        web=WebToolConfig(provider=str(_as_mapping(tools_data.get("web")).get("provider", "urllib"))),
        scanner=ScannerToolConfig(
            executable=scanner_provider_config.executable,
            extra_args=scanner_provider_config.extra_args,
            env=scanner_provider_config.env,
            working_directory=scanner_provider_config.working_directory,
        ),
    )


def _build_paths(data: Mapping[str, Any]) -> PathsConfig:
    return PathsConfig(
        project_root=str(data.get("project_root", ".")),
        benchmark_dir=str(data.get("benchmark_dir", "data/benchmarks")),
        result_dir=str(data.get("result_dir", "data/results")),
    )


def load_app_config(path: str | Path | Sequence[str | Path]) -> AppConfig:
    paths: list[Path]
    if isinstance(path, (str, Path)):
        paths = [Path(path)]
    else:
        paths = [Path(item) for item in path]

    raw: dict[str, Any] = {}
    for config_path in paths:
        raw = _merge_dicts(raw, _load_merged_yaml(config_path))

    return AppConfig(
        workflow=_build_workflow(_as_mapping(raw.get("workflow", raw.get("psm", {})))),
        llm=_build_llm(raw),
        optimization=_build_optimization(_as_mapping(raw.get("optimization", {}))),
        runtime=_build_runtime(raw),
        tools=_build_tools(raw),
        paths=_build_paths(_as_mapping(raw.get("paths", {}))),
    )

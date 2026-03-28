from __future__ import annotations

import argparse
import json
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from autopt.analysis.cli import configure_analysis_subcommands, handle_analysis_command
from autopt.benchmark.loader import find_benchmark_by_name, load_benchmarks
from autopt.config import AppConfig, load_app_config
from autopt.models.registry import ModelSpec, resolve_model
from autopt.prompts import list_prompt_bundle_names
from autopt.runner.experiment_runner import ExperimentRequest, ExperimentRunner
from autopt.runner.result_writer import write_jsonl_record
from autopt.runner.task_runner import TaskRunner, build_task_request
from autopt.tools.terminal import InteractiveShell


DEFAULT_MAINLINE_CONFIG = Path("configs/config.yml")
DEFAULT_MAINLINE_CONFIG_EXAMPLE = Path("configs/config.example.yml")
DEFAULT_LEGACY_CONFIG = Path("Opti-AutoPT/config/config.yml")
MODEL_HELP = (
    "Optional model identifier. Use `provider:model_name` for an explicit provider, "
    "or just `model_name` to use llm.default_provider. Defaults to llm.default_model."
)
BENCHMARK_HELP = (
    "Inspect benchmark files and list the available benchmark item names before running tasks."
)
DOCTOR_HELP = (
    "Check whether the current configuration, shell runtime, model provider, scanner, and optional benchmark file "
    "are ready for use."
)
EXPERIMENT_HELP = (
    "Batch experiment mode. Explicitly pass the benchmark file, model list, and repeat count here.\n"
    "This subcommand uses config.yml for runtime/LLM/tool settings only, not for experiment targets."
)
DOCTOR_EPILOG = (
    "Examples:\n"
    "  uv run autopt doctor\n"
    "  uv run autopt doctor --benchmark-file <path-to-benchmark.jsonl>\n"
    "  uv run autopt doctor --model openai:gpt-5.2"
)
EXPERIMENT_EPILOG = (
    "Examples:\n"
    "  autopt experiment --benchmark-file <path-to-benchmark.jsonl> \\\n"
    "    --models openai:gpt-5.2 --ip-addr 127.0.0.1:8080\n\n"
    "  autopt experiment --benchmark-file <path-to-benchmark.jsonl> \\\n"
    "    --benchmark-name thinkphp/5-rce drupal/CVE-2018-7600 \\\n"
    "    --models openai:gpt-5.2 openai:gpt-4o \\\n"
    "    --repeat 3 --output-file data/results/experiment.jsonl --ip-addr 127.0.0.1:8080"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AutoPT unified CLI.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Inspect benchmark files.",
        description=BENCHMARK_HELP,
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(dest="benchmark_command", required=True)
    benchmark_list_parser = benchmark_subparsers.add_parser(
        "list",
        help="List benchmark item names from a benchmark JSONL file.",
    )
    benchmark_list_parser.add_argument("--benchmark-file", required=True, help="Path to benchmark JSONL.")
    benchmark_list_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include target, category, and difficulty information.",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Inspect a benchmark and model mapping without running the workflow.",
    )
    inspect_parser.add_argument("--benchmark-file", required=True, help="Path to benchmark JSONL.")
    inspect_parser.add_argument("--benchmark-name", required=True, help="Benchmark item name.")
    inspect_parser.add_argument("--model", default=None, help=MODEL_HELP)
    inspect_parser.add_argument(
        "--config-file",
        default=None,
        help="Optional YAML config file. Used to resolve llm.default_provider and llm.default_model.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run one benchmark task through the shared workflow.",
    )
    run_parser.add_argument("--benchmark-file", required=True, help="Path to benchmark JSONL.")
    run_parser.add_argument("--benchmark-name", required=True, help="Benchmark item name.")
    run_parser.add_argument("--model", default=None, help=MODEL_HELP)
    run_parser.add_argument("--ip-addr", required=True, help="Target ip:port.")
    run_parser.add_argument(
        "--prompt-bundle",
        default="default",
        choices=list_prompt_bundle_names(),
        help="Prompt bundle name.",
    )
    run_parser.add_argument(
        "--config-file",
        default=None,
        help="Optional YAML config file. Defaults to configs/config.yml if present.",
    )
    run_parser.add_argument(
        "--output-file",
        default=None,
        help="Optional JSONL file for writing the task result.",
    )

    experiment_parser = subparsers.add_parser(
        "experiment",
        help="Run batch experiments through the shared workflow.",
        description=EXPERIMENT_HELP,
        epilog=EXPERIMENT_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    experiment_parser.add_argument(
        "--benchmark-file",
        required=True,
        help="Benchmark JSONL path for this experiment run.",
    )
    experiment_parser.add_argument(
        "--benchmark-name",
        nargs="*",
        default=None,
        help="Optional benchmark names. Omit to run all benchmarks in the benchmark file.",
    )
    experiment_parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help=(
            "One or more model identifiers. Each item accepts `provider:model_name` "
            "or `model_name`."
        ),
    )
    experiment_parser.add_argument(
        "--prompt-bundle",
        default="default",
        choices=list_prompt_bundle_names(),
        help="Prompt bundle name.",
    )
    experiment_parser.add_argument("--ip-addr", required=True, help="Target ip:port.")
    experiment_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of rounds to repeat each benchmark x model combination. Defaults to 1.",
    )
    experiment_parser.add_argument(
        "--config-file",
        default=None,
        help="Optional YAML config file for runtime, LLM, tool, and workflow settings.",
    )
    experiment_parser.add_argument(
        "--output-file",
        default=None,
        help="Optional JSONL output path. Defaults to data/results/experiment_<timestamp>.jsonl.",
    )

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze result JSONL files through the shared analysis module.",
    )
    configure_analysis_subcommands(analyze_parser)

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Check whether the environment is ready for use.",
        description=DOCTOR_HELP,
        epilog=DOCTOR_EPILOG,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    doctor_parser.add_argument(
        "--config-file",
        default=None,
        help="Optional YAML config file. Defaults to configs/config.yml when present.",
    )
    doctor_parser.add_argument(
        "--benchmark-file",
        default=None,
        help="Optional benchmark JSONL path to validate.",
    )
    doctor_parser.add_argument(
        "--model",
        default=None,
        help="Optional model identifier to validate. Defaults to llm.default_model.",
    )

    return parser


def _resolve_config_bundle(config_file: str | None) -> tuple[AppConfig, Path | None, str]:
    if config_file:
        path = Path(config_file)
        return load_app_config(path), path, "explicit"
    if DEFAULT_MAINLINE_CONFIG.exists():
        return load_app_config(DEFAULT_MAINLINE_CONFIG), DEFAULT_MAINLINE_CONFIG, "config"
    if DEFAULT_MAINLINE_CONFIG_EXAMPLE.exists():
        return load_app_config(DEFAULT_MAINLINE_CONFIG_EXAMPLE), DEFAULT_MAINLINE_CONFIG_EXAMPLE, "example"
    if DEFAULT_LEGACY_CONFIG.exists():
        return load_app_config(DEFAULT_LEGACY_CONFIG), DEFAULT_LEGACY_CONFIG, "legacy"
    return AppConfig(), None, "defaults"


def _resolve_config(config_file: str | None) -> AppConfig:
    return _resolve_config_bundle(config_file)[0]


def _resolve_benchmark_file(benchmark_file: str) -> Path:
    resolved_path = Path(benchmark_file)
    if resolved_path.exists():
        return resolved_path
    raise ValueError(f"Benchmark file does not exist: {resolved_path}")


def _default_experiment_output_path() -> Path:
    base_dir = Path("data/results")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return base_dir / f"experiment_{timestamp}.jsonl"


def _resolve_model_spec(model_identifier: str | None, config: AppConfig) -> ModelSpec:
    candidate = (model_identifier or config.llm.default_model or "").strip()
    if not candidate:
        raise ValueError(
            "No model configured. Pass --model explicitly or set llm.default_model in configs/config.yml."
        )
    return resolve_model(candidate, default_provider=config.llm.default_provider)


def _format_benchmark_row(name: str, *, target: str = "", category: str = "", difficulty: str = "") -> str:
    parts = [name]
    if category:
        parts.append(f"category={category}")
    if difficulty:
        parts.append(f"difficulty={difficulty}")
    if target:
        parts.append(f"target={target}")
    return " | ".join(parts)


def _build_scanner_check_command(executable: str) -> str:
    quoted = shlex.quote(executable)
    if "/" in executable:
        return f"if [ -x {quoted} ]; then printf %s {quoted}; else exit 1; fi"
    return f"command -v {quoted}"


def handle_benchmark_list(benchmark_file: str, *, verbose: bool = False) -> int:
    items = load_benchmarks(_resolve_benchmark_file(benchmark_file))
    for item in items:
        if verbose:
            print(
                _format_benchmark_row(
                    item.name,
                    target=item.target,
                    category=item.category,
                    difficulty=item.difficulty,
                )
            )
        else:
            print(item.name)
    return 0


def handle_benchmark_command(args: argparse.Namespace) -> int:
    if args.benchmark_command == "list":
        return handle_benchmark_list(args.benchmark_file, verbose=args.verbose)
    raise ValueError(f"Unsupported benchmark command: {args.benchmark_command}")


def handle_doctor(
    *,
    config_file: str | None = None,
    benchmark_file: str | None = None,
    model_identifier: str | None = None,
) -> int:
    config, config_source, source_kind = _resolve_config_bundle(config_file)
    checks: list[tuple[str, str, str]] = []

    def add_check(status: str, name: str, detail: str) -> None:
        checks.append((status, name, detail))

    if source_kind in {"explicit", "config"} and config_source is not None:
        add_check("pass", "config", f"Loaded configuration from `{config_source}`.")
    elif source_kind == "example" and config_source is not None:
        add_check(
            "warn",
            "config",
            f"Using template fallback `{config_source}`. Copy it to `configs/config.yml` for normal use.",
        )
    elif source_kind == "legacy" and config_source is not None:
        add_check("warn", "config", f"Using legacy fallback config `{config_source}`.")
    else:
        add_check("warn", "config", "No config file found. Falling back to in-code defaults.")

    model: ModelSpec | None = None
    try:
        model = _resolve_model_spec(model_identifier, config)
        model_source = "--model" if model_identifier else "llm.default_model"
        add_check("pass", "model", f"Resolved {model_source} to `{model.alias}`.")
    except Exception as exc:
        add_check("fail", "model", str(exc))

    if model is not None:
        provider_config = config.llm.get_provider(model.provider)
        if provider_config.api_key.strip():
            add_check("pass", "provider", f"API key configured for provider `{model.provider}`.")
        else:
            add_check(
                "fail",
                "provider",
                f"Missing `api_key` for provider `{model.provider}` under `llm.providers.{model.provider}`.",
            )

    scanner_provider = config.tools.scanner.to_command_provider_config()
    runtime_shell_ok = False
    shell: InteractiveShell | None = None

    try:
        shell = InteractiveShell(config.runtime, scanner_provider=scanner_provider)
        runtime_result = shell.execute("printf autopt-doctor")
        if runtime_result.exit_code == 0 and "autopt-doctor" in runtime_result.output:
            if config.runtime.provider == "local":
                add_check("pass", "runtime", "Local shell command execution works.")
            else:
                add_check(
                    "pass",
                    "runtime",
                    f"Remote SSH shell command execution works via `{config.runtime.ssh.host}:{config.runtime.ssh.port}`.",
                )
            runtime_shell_ok = True
        else:
            add_check(
                "fail",
                "runtime",
                f"Shell test command failed with exit code {runtime_result.exit_code}.",
            )
    except Exception as exc:
        if config.runtime.provider == "ssh" and not config.runtime.ssh.host.strip():
            add_check("fail", "runtime", "runtime.provider is `ssh` but runtime.ssh.host is empty.")
        else:
            add_check("fail", "runtime", f"Unable to initialize `{config.runtime.provider}` shell: {exc}")

    if runtime_shell_ok and shell is not None:
        executable = scanner_provider.executable.strip() or "xray"
        try:
            scanner_result = shell.execute(_build_scanner_check_command(executable))
            resolved_scanner = scanner_result.output.strip()
            if scanner_result.exit_code == 0 and resolved_scanner:
                add_check("pass", "scanner", f"Scanner executable is available as `{resolved_scanner}`.")
            else:
                add_check(
                    "fail",
                    "scanner",
                    f"Configured scanner executable `{executable}` is not available in the runtime shell.",
                )
        except Exception as exc:
            add_check("fail", "scanner", f"Unable to validate scanner executable: {exc}")
    else:
        add_check("warn", "scanner", "Scanner validation skipped because the runtime shell is unavailable.")

    if shell is not None:
        shell.close()

    if benchmark_file:
        try:
            benchmark_items = load_benchmarks(_resolve_benchmark_file(benchmark_file))
            add_check("pass", "benchmark", f"Loaded {len(benchmark_items)} benchmark item(s) from `{benchmark_file}`.")
        except Exception as exc:
            add_check("fail", "benchmark", str(exc))
    else:
        add_check("warn", "benchmark", "No benchmark file provided. Pass --benchmark-file to validate benchmark input.")

    failed = sum(1 for status, _, _ in checks if status == "fail")
    warned = sum(1 for status, _, _ in checks if status == "warn")
    passed = sum(1 for status, _, _ in checks if status == "pass")

    for status, name, detail in checks:
        print(f"[{status.upper():4}] {name}: {detail}")
    print(f"\nSummary: {passed} passed, {warned} warning(s), {failed} failed.")
    return 1 if failed else 0


def handle_inspect(
    benchmark_file: str,
    benchmark_name: str,
    model_identifier: str | None = None,
    config_file: str | None = None,
) -> int:
    config = _resolve_config(config_file)
    benchmark = find_benchmark_by_name(Path(benchmark_file), benchmark_name)
    model = _resolve_model_spec(model_identifier, config)
    payload = {
        "benchmark": benchmark.to_dict(),
        "model": model.to_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def handle_run(
    benchmark_file: str,
    benchmark_name: str,
    model_identifier: str | None,
    ip_addr: str,
    prompt_bundle_name: str = "default",
    config_file: str | None = None,
    output_file: str | None = None,
) -> int:
    config = _resolve_config(config_file)
    benchmark = find_benchmark_by_name(Path(benchmark_file), benchmark_name)
    model = _resolve_model_spec(model_identifier, config)
    request = build_task_request(
        benchmark=benchmark,
        model=model,
        ip_addr=ip_addr,
        config=config,
        prompt_bundle_name=prompt_bundle_name,
    )
    result = TaskRunner().run(request)
    payload = result.to_dict()

    if output_file:
        write_jsonl_record(output_file, payload)

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if result.status != "error" else 1


def handle_experiment(
    benchmark_file: str,
    benchmark_names: list[str] | None,
    model_identifiers: list[str],
    ip_addr: str,
    repeat: int,
    prompt_bundle_name: str = "default",
    config_file: str | None = None,
    output_file: str | None = None,
) -> int:
    config = _resolve_config(config_file)
    resolved_benchmark_file = _resolve_benchmark_file(benchmark_file)
    resolved_output_file = Path(output_file) if output_file else _default_experiment_output_path()

    request = ExperimentRequest(
        benchmark_file=resolved_benchmark_file,
        benchmark_names=benchmark_names or [],
        model_identifiers=model_identifiers,
        ip_addr=ip_addr,
        repeat=repeat,
        config=config,
        output_file=resolved_output_file,
        prompt_bundle_name=prompt_bundle_name,
    )
    runner = ExperimentRunner()
    report = runner.run(request)
    payload = report.to_dict()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["summary"].get("error", 0) == 0 else 1


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "benchmark":
        return handle_benchmark_command(args)
    if args.command == "inspect":
        return handle_inspect(args.benchmark_file, args.benchmark_name, args.model, args.config_file)
    if args.command == "run":
        return handle_run(
            args.benchmark_file,
            args.benchmark_name,
            args.model,
            args.ip_addr,
            args.prompt_bundle,
            args.config_file,
            args.output_file,
        )
    if args.command == "experiment":
        return handle_experiment(
            args.benchmark_file,
            args.benchmark_name,
            args.models,
            args.ip_addr,
            args.repeat,
            args.prompt_bundle,
            args.config_file,
            args.output_file,
        )
    if args.command == "analyze":
        return handle_analysis_command(args)
    if args.command == "doctor":
        return handle_doctor(
            config_file=args.config_file,
            benchmark_file=args.benchmark_file,
            model_identifier=args.model,
        )
    raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

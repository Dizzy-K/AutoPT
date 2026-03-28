# Auto-RT Project Guide

中文版本: [README.md](README.md)

### Overview

The top-level packages `analysis/`, `benchmark/`, `cli/`, `config/`, `models/`, `prompts/`, `runner/`, `tools/`, and `workflow/` contain the core Auto-RT system. It is designed for research on LLM-based automated red teaming over reproducible vulnerable targets, including scanning, vulnerability interpretation, exploit planning, execution, and result analysis.

The project currently supports:

- environment diagnostics
- benchmark inspection
- single-task execution
- batch experiments
- normalized result analysis

### Structure

```text
.
├── analysis/      # normalization, summary, failure analysis, plotting
├── benchmark/     # benchmark loading and data models
├── cli/           # benchmark / inspect / run / experiment / analyze / doctor
├── config/        # config schema and loader
├── configs/       # config template
├── models/        # model registry and provider adapters
├── prompts/       # prompt bundles and layering
├── runner/        # task and experiment runners
├── tools/         # terminal / web / scanner provider adapters
└── workflow/      # workflow, nodes, parsing, state routing
```

### Installation

Dependencies are defined in a single file at the repository root: [`pyproject.toml`](pyproject.toml).

```bash
pip install -e .
```

Optional dependency groups from the same file:

```bash
pip install -e '.[analysis]'
pip install -e '.[legacy]'
pip install -e '.[dev]'
pip install -e '.[analysis,legacy,dev]'
```

### Runtime Requirements

The project requires:

- Python 3.10+
- a local Linux shell or a reachable remote Linux shell over SSH
- a scanner such as `xray` installed in the environment where commands actually run
- access to vulnerable benchmark targets

Kali is not strictly required. For most reproductions, a standard Ubuntu or Debian attacker host is sufficient.

### Configuration

The repository provides a single config template:

- [`configs/config.example.yml`](configs/config.example.yml)

Recommended initialization:

```bash
cp configs/config.example.yml configs/config.yml
```

For normal use, edit `configs/config.yml` directly.
`runtime.provider` supports `local` and `ssh`. The default `local` mode executes commands on the current machine; switch it to `ssh` to run commands on a remote attack host described by `runtime.ssh`.
Pass batch experiment targets, model lists, and repeat counts explicitly to the `experiment` subcommand.

Minimal config examples:

Local execution + OpenAI model

```yaml
llm:
  default_provider: openai
  default_model: "openai:gpt-5.2"
  providers:
    openai:
      api_key: "your-openai-key"

runtime:
  provider: local
```

Remote execution + OpenAI model

```yaml
llm:
  default_provider: openai
  default_model: "openai:gpt-5.2"
  providers:
    openai:
      api_key: "your-openai-key"

runtime:
  provider: ssh
  ssh:
    host: "attacker-host"
    port: 22
    username: "root"
    password: "your-password"
    timeout: 30
```

Notes:

- Only fill the provider keys you actually use; unused providers can stay empty or be removed.
- If `xray` is not on PATH, set an absolute path in `tools.scanner.executable`.

### Benchmarks and Data

The current checkout does not include bundled benchmark data files. Before running `inspect`, `run`, or `experiment`, prepare your own benchmark JSONL file and pass it explicitly with `--benchmark-file`.

The `--benchmark-name` used by `inspect` and `run` must exactly match an item name in that JSONL file.
You can list available names first with `autort benchmark list --benchmark-file <path-to-benchmark.jsonl>`.

### Quick Start

#### 1. Check the environment and config

```bash
autort doctor --config-file configs/config.yml
```

#### 2. List benchmark names

```bash
autort benchmark list --benchmark-file <path-to-benchmark.jsonl>
```

#### 3. Inspect a benchmark item

```bash
autort inspect \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name>'
```

If `llm.default_model` is set in `configs/config.yml`, both `inspect` and `run` can omit `--model`; keep `--model` only for one-off overrides.

#### 4. Run a single task

```bash
autort run \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name>' \
  --ip-addr '<target-ip:port>' \
  --config-file configs/config.yml \
  --output-file data/results/task_result.jsonl
```

#### 5. Run batch experiments

```bash
autort experiment \
  --benchmark-file <path-to-benchmark.jsonl> \
  --models openai:gpt-5.2 \
  --ip-addr '<target-ip:port>' \
  --repeat 1 \
  --config-file configs/config.yml \
  --output-file data/results/experiment.jsonl
```

#### 6. Analyze results

```bash
autort analyze summary data/results/experiment.jsonl
autort analyze fail-reasons data/results/experiment.jsonl
autort analyze matrix data/results/experiment.jsonl
```

### CLI Arguments

#### `benchmark list`

Purpose: list benchmark item names from a benchmark JSONL file before using `inspect`, `run`, or `experiment --benchmark-name`.

| Argument | Required | Description |
| --- | --- | --- |
| `--benchmark-file` | Yes | path to the benchmark JSONL file |
| `--verbose` | No | include `category`, `difficulty`, and `target` in the output |

#### `inspect`

Purpose: inspect a benchmark item and model mapping without executing the workflow.

| Argument | Required | Description |
| --- | --- | --- |
| `--benchmark-file` | Yes | path to the benchmark JSONL file |
| `--benchmark-name` | Yes | benchmark item name, for example `thinkphp/5-rce` |
| `--model` | No | model identifier; use `provider:model_name`, or just `model_name` to use `llm.default_provider`; defaults to `llm.default_model` |
| `--config-file` | No | YAML config path used to resolve `llm.default_provider` and `llm.default_model` |

#### `run`

Purpose: execute a single benchmark task.

| Argument | Required | Description |
| --- | --- | --- |
| `--benchmark-file` | Yes | path to the benchmark JSONL file |
| `--benchmark-name` | Yes | target benchmark item name |
| `--model` | No | model identifier; use `provider:model_name`, or just `model_name`; defaults to `llm.default_model` |
| `--ip-addr` | Yes | target address, typically in `ip:port` form |
| `--prompt-bundle` | No | prompt bundle name, default `default` |
| `--config-file` | No | YAML config path; defaults to `configs/config.yml` when available |
| `--output-file` | No | JSONL output path for the task result |

#### `experiment`

Purpose: execute batch experiments.

| Argument | Required | Description |
| --- | --- | --- |
| `--benchmark-file` | Yes | benchmark JSONL path for this experiment run |
| `--benchmark-name` | No | one or more benchmark names; omit to run all items in the benchmark file |
| `--models` | Yes | one or more model identifiers; each item supports `provider:model_name` or `model_name` |
| `--ip-addr` | Yes | target address, typically in `ip:port` form |
| `--repeat` | No | repeat count; defaults to `1` |
| `--prompt-bundle` | No | prompt bundle name, default `default` |
| `--config-file` | No | YAML config path; only affects runtime, provider, tool, and workflow settings |
| `--output-file` | No | JSONL output path for experiment results; defaults to `data/results/experiment_<timestamp>.jsonl` |

Note:
The `experiment` subcommand no longer reads benchmark targets, model lists, or repeat counts from `config.yml`; pass those orchestration inputs explicitly on the CLI.

Multi-value example:

```bash
autort experiment \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name-1>' '<benchmark-name-2>' \
  --models openai:gpt-5.2 openai:gpt-4o \
  --ip-addr '<target-ip:port>'
```

#### `doctor`

Purpose: check whether the current config, model provider, command runtime, scanner, and optional benchmark file are ready for use.

| Argument | Required | Description |
| --- | --- | --- |
| `--config-file` | No | YAML config path; defaults to `configs/config.yml` when available |
| `--benchmark-file` | No | optional benchmark JSONL path to validate |
| `--model` | No | optional model identifier; defaults to `llm.default_model` |

#### `analyze`

Purpose: normalize and analyze result files.

First-level subcommands:

- `summary`
- `export-csv`
- `matrix`
- `history`
- `fail-commands`
- `fail-reasons`
- `plot`

Common arguments:

| Argument | Required | Description |
| --- | --- | --- |
| `inputs` | Yes | one or more JSONL files, or directories containing JSONL files |
| `--benchmark-file` | No | benchmark JSONL for metadata enrichment; can be passed multiple times |
| `--benchmark-name` | No | filter by benchmark name |
| `--model` | No | filter by the model identifier stored in the result |
| `--arch` | No | filter by architecture label |
| `--status` | No | filter by execution status |
| `--difficulty` | No | filter by benchmark difficulty |
| `--category` | No | filter by benchmark category |
| `--workflow-name` | No | filter by workflow name |
| `--prompt-bundle-name` | No | filter by prompt bundle name |

Subcommand-specific arguments:

| Subcommand | Arguments | Description |
| --- | --- | --- |
| `summary` | `--output` | optional JSON output path |
| `export-csv` | `--output` | required CSV output path |
| `matrix` | `--rows` / `--cols` / `--metric` / `--output` | matrix grouping, metric, and output options |
| `history` | `--parsed` | parse workflow history entries |
| `fail-commands` | `--group-by` | grouping field for failed commands |
| `fail-reasons` | `--group-by` | grouping field for failure reasons |
| `plot` | `--x` / `--series` / `--metric` / `--output` / `--title` / `--ylabel` | grouped bar chart options |

### Verification

The current checkout does not include a directly runnable automated test directory. Recommended basic checks:

```bash
autort --help
autort doctor --config-file configs/config.example.yml
autort experiment --help
autort benchmark list --help
python -m compileall config cli models runner tools workflow
```

If these commands succeed, the packaging entrypoint, CLI wiring, and major module imports are at least in a usable state.

### Limitations

- The project requires an external attacker shell and benchmark environment.
- Benchmark data files must be prepared by the user.
- Browser automation is not part of the default tool profile.

### Safety

This project is intended for authorized security research, benchmark evaluation, and controlled red-team experimentation only.

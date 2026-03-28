# Auto-RT

English version: [README_EN.md](README_EN.md)

### 项目简介

仓库根目录下的 `analysis/`、`benchmark/`、`cli/`、`config/`、`models/`、`prompts/`、`runner/`、`tools/`、`workflow/` 共同构成 Auto-RT 的核心系统实现，用于在可复现漏洞靶场上研究 LLM agent 的扫描、漏洞理解、利用规划、执行与结果分析能力。

当前项目统一提供以下能力：

- 环境自检
- benchmark 检查
- 单任务执行
- 批量实验
- 结果归一化与分析

### 目录说明

```text
.
├── analysis/      # 结果归一化、汇总、失败分析、绘图
├── benchmark/     # benchmark 加载与数据模型
├── cli/           # benchmark / inspect / run / experiment / analyze / doctor
├── config/        # 配置 schema 与 loader
├── configs/       # 配置模板
├── models/        # 模型注册与 provider 适配
├── prompts/       # prompt bundle 与分层逻辑
├── runner/        # task / experiment 执行器
├── tools/         # terminal / web / scanner provider 适配
└── workflow/      # agent workflow、节点、解析、状态路由
```

### 安装方式

依赖入口统一为仓库根目录的 [`pyproject.toml`](pyproject.toml)。

```bash
pip install -e .
```

如果需要同一文件中的可选依赖组：

```bash
pip install -e '.[analysis]'
pip install -e '.[legacy]'
pip install -e '.[dev]'
pip install -e '.[analysis,legacy,dev]'
```

### 运行要求

- Python 3.10+
- 一个本地 Linux shell，或一个可通过 SSH 访问的远程 Linux shell
- 在实际执行命令的环境中已安装扫描器，例如 `xray`
- 可访问的漏洞靶场环境

项目并不强制要求 Kali。对复现实验而言，Ubuntu / Debian 攻击机通常已经足够。

### 配置方式

仓库提供一份配置模板：

- [`configs/config.example.yml`](configs/config.example.yml)

推荐初始化方式：

```bash
cp configs/config.example.yml configs/config.yml
```

日常使用时直接修改 `configs/config.yml` 即可。
其中 `runtime.provider` 支持 `local` 和 `ssh`。默认 `local` 表示在当前机器直接执行命令；改成 `ssh` 时，命令会通过 `runtime.ssh` 登录到远程攻击机执行。
批量实验的 benchmark、模型列表和重复次数通过 `experiment` 子命令显式传入。

最小配置示例：

本地执行 + OpenAI 模型

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

远程执行 + OpenAI 模型

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

补充说明：

- 只需要填写你实际使用的 provider key；不用的 provider 可以留空或删掉。
- 如果 `xray` 不在 PATH 中，可以在 `tools.scanner.executable` 里改成绝对路径。

### 数据与 benchmark

当前 checkout 不包含可直接使用的 benchmark 数据文件。运行 `inspect`、`run`、`experiment` 之前，请先准备自己的 benchmark JSONL 文件，并在命令行里显式传入 `--benchmark-file`。

`inspect` 和 `run` 使用的 `--benchmark-name` 必须精确匹配该 JSONL 文件中的条目名称。
可以先用 `autort benchmark list --benchmark-file <path-to-benchmark.jsonl>` 查看可用名称。

### 快速开始

#### 1. 检查环境与配置

```bash
autort doctor --config-file configs/config.yml
```

#### 2. 列出 benchmark 名称

```bash
autort benchmark list --benchmark-file <path-to-benchmark.jsonl>
```

#### 3. 检查 benchmark 样本

```bash
autort inspect \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name>'
```

如果已经在 `configs/config.yml` 里设置了 `llm.default_model`，`inspect` 和 `run` 可以不再重复传 `--model`；只有临时覆盖时再显式指定。

#### 4. 执行单个任务

```bash
autort run \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name>' \
  --ip-addr '<target-ip:port>' \
  --config-file configs/config.yml \
  --output-file data/results/task_result.jsonl
```

#### 5. 执行批量实验

```bash
autort experiment \
  --benchmark-file <path-to-benchmark.jsonl> \
  --models openai:gpt-5.2 \
  --ip-addr '<target-ip:port>' \
  --repeat 1 \
  --config-file configs/config.yml \
  --output-file data/results/experiment.jsonl
```

#### 6. 分析结果

```bash
autort analyze summary data/results/experiment.jsonl
autort analyze fail-reasons data/results/experiment.jsonl
autort analyze matrix data/results/experiment.jsonl
```

### 命令行参数说明

#### `benchmark list`

用途：列出 benchmark JSONL 文件中的条目名称，便于后续传给 `inspect`、`run` 或 `experiment --benchmark-name`。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--benchmark-file` | 是 | benchmark JSONL 文件路径 |
| `--verbose` | 否 | 输出 `category`、`difficulty`、`target` 等附加信息 |

#### `inspect`

用途：检查 benchmark 样本与模型映射，不执行 workflow。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--benchmark-file` | 是 | benchmark JSONL 文件路径 |
| `--benchmark-name` | 是 | benchmark 条目名称，例如 `thinkphp/5-rce` |
| `--model` | 否 | 模型标识；支持 `provider:model_name`，或仅写 `model_name` 使用 `llm.default_provider`；不传时使用 `llm.default_model` |
| `--config-file` | 否 | YAML 配置文件路径；用于解析 `llm.default_provider` 与 `llm.default_model` |

#### `run`

用途：执行单个 benchmark 任务。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--benchmark-file` | 是 | benchmark JSONL 文件路径 |
| `--benchmark-name` | 是 | 目标 benchmark 条目名称 |
| `--model` | 否 | 模型标识；支持 `provider:model_name`，或仅写 `model_name`；不传时使用 `llm.default_model` |
| `--ip-addr` | 是 | 靶场地址，通常为 `ip:port` |
| `--prompt-bundle` | 否 | prompt bundle 名称，默认 `default` |
| `--config-file` | 否 | YAML 配置文件路径，默认优先使用 `configs/config.yml` |
| `--output-file` | 否 | task result JSONL 输出路径 |

#### `experiment`

用途：批量执行实验。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--benchmark-file` | 是 | 本次实验使用的 benchmark JSONL 路径 |
| `--benchmark-name` | 否 | 一个或多个 benchmark 名称；不传则运行该文件中的全部条目 |
| `--models` | 是 | 一个或多个模型标识；每项支持 `provider:model_name`，或仅写 `model_name` |
| `--ip-addr` | 是 | 靶场地址，通常为 `ip:port` |
| `--repeat` | 否 | 重复轮数；默认 `1` |
| `--prompt-bundle` | 否 | prompt bundle 名称，默认 `default` |
| `--config-file` | 否 | YAML 配置文件路径；只影响运行环境、模型 provider、工具与 workflow 设置 |
| `--output-file` | 否 | experiment result 输出路径；不传则自动写到 `data/results/experiment_<timestamp>.jsonl` |

说明：
`experiment` 子命令现在不再从 `config.yml` 读取 benchmark、模型列表或重复次数；这些实验编排参数都要求在命令行中显式给出。

多值参数示例：

```bash
autort experiment \
  --benchmark-file <path-to-benchmark.jsonl> \
  --benchmark-name '<benchmark-name-1>' '<benchmark-name-2>' \
  --models openai:gpt-5.2 openai:gpt-4o \
  --ip-addr '<target-ip:port>'
```

#### `doctor`

用途：检查当前配置、模型 provider、命令执行环境、扫描器以及可选 benchmark 文件是否可用。

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `--config-file` | 否 | YAML 配置文件路径；默认优先使用 `configs/config.yml` |
| `--benchmark-file` | 否 | 可选 benchmark JSONL 文件路径，用于检查 benchmark 是否可读 |
| `--model` | 否 | 可选模型标识；不传时使用 `llm.default_model` |

#### `analyze`

用途：对结果文件进行归一化分析。

一级子命令：

- `summary`
- `export-csv`
- `matrix`
- `history`
- `fail-commands`
- `fail-reasons`
- `plot`

通用参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `inputs` | 是 | 一个或多个 JSONL 文件，或包含 JSONL 的目录 |
| `--benchmark-file` | 否 | 用于补充 benchmark 元数据，可重复传入多次 |
| `--benchmark-name` | 否 | 按 benchmark 名称过滤 |
| `--model` | 否 | 按结果中的模型标识过滤 |
| `--arch` | 否 | 按架构标签过滤 |
| `--status` | 否 | 按执行状态过滤 |
| `--difficulty` | 否 | 按难度过滤 |
| `--category` | 否 | 按类别过滤 |
| `--workflow-name` | 否 | 按 workflow 名称过滤 |
| `--prompt-bundle-name` | 否 | 按 prompt bundle 名称过滤 |

子命令附加参数：

| 子命令 | 参数 | 说明 |
| --- | --- | --- |
| `summary` | `--output` | 可选 JSON 输出路径 |
| `export-csv` | `--output` | 必填，CSV 输出路径 |
| `matrix` | `--rows` / `--cols` / `--metric` / `--output` | 指定矩阵行列分组、指标与输出路径 |
| `history` | `--parsed` | 解析 workflow history 条目 |
| `fail-commands` | `--group-by` | 指定失败命令聚合维度 |
| `fail-reasons` | `--group-by` | 指定失败原因聚合维度 |
| `plot` | `--x` / `--series` / `--metric` / `--output` / `--title` / `--ylabel` | 绘图参数 |

### 验证方式

当前 checkout 不包含可直接运行的自动化测试目录。建议先做以下基础校验：

```bash
autort --help
autort doctor --config-file configs/config.example.yml
autort experiment --help
autort benchmark list --help
python -m compileall config cli models runner tools workflow
```

如果上述命令都正常，通常说明打包入口、CLI 装配和主要模块导入至少处于可用状态。

### 限制说明

- 项目运行依赖外部攻击机 shell 与靶场环境。
- benchmark 数据文件需要由使用者自行准备。
- 浏览器自动化类工具当前不属于默认工具集。

### 安全

本项目仅用于授权安全研究、benchmark 评估与受控红队实验。请勿在未授权目标上使用。

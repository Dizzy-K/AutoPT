from __future__ import annotations

"""Pydantic configuration models for AutoPT runtime, LLM, tools, and workflow settings."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class ModelProviderConfig:
    openai_base: str = ""
    openai_key: str = ""
    nvidia_key: str = ""
    together_key: str = ""
    temperature: float = 0.0


@dataclass(slots=True)
class LLMProviderConfig:
    api_base: str = ""
    api_key: str = ""
    temperature: float | None = None


@dataclass(slots=True)
class LLMConfig:
    default_provider: str = "openai"
    default_model: str = ""
    temperature: float = 0.0
    providers: dict[str, LLMProviderConfig] = field(default_factory=dict)

    def get_provider(self, provider_name: str) -> LLMProviderConfig:
        source = self.providers.get(provider_name, LLMProviderConfig())
        return LLMProviderConfig(
            api_base=source.api_base,
            api_key=source.api_key,
            temperature=self.temperature if source.temperature is None else source.temperature,
        )

    def as_legacy_provider_config(self) -> ModelProviderConfig:
        openai = self.get_provider("openai")
        nvidia = self.get_provider("nvidia")
        together = self.get_provider("together")
        return ModelProviderConfig(
            openai_base=openai.api_base,
            openai_key=openai.api_key,
            nvidia_key=nvidia.api_key,
            together_key=together.api_key,
            temperature=self.temperature,
        )


@dataclass(slots=True)
class WorkflowConfig:
    sys_iterations: int = 15
    exp_iterations: int = 1
    query_iterations: int = 1
    scan_iterations: int = 1
    debug: bool = False
    draw_graph: bool = False


@dataclass(slots=True)
class OptimizationConfig:
    enabled: bool = False
    model: str = "gpt-4"
    optimize_states: list[str] = field(default_factory=lambda: ["scan", "inquire", "exploit"])

    @property
    def isopt(self) -> bool:
        return self.enabled


@dataclass(slots=True)
class SSHConfig:
    host: str = ""
    port: int = 22
    username: str = "root"
    password: str = ""
    timeout: int = 30


@dataclass(slots=True)
class RuntimeConfig:
    provider: str = "local"
    ssh: SSHConfig = field(default_factory=SSHConfig)


@dataclass(slots=True)
class CommandToolProviderConfig:
    executable: str = ""
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_directory: str = ""


@dataclass(slots=True)
class TerminalToolConfig:
    provider: str = "ssh"


@dataclass(slots=True)
class WebToolConfig:
    provider: str = "urllib"


@dataclass(slots=True)
class ScannerToolConfig:
    executable: str = "xray"
    extra_args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    working_directory: str = ""

    def to_command_provider_config(self) -> CommandToolProviderConfig:
        return CommandToolProviderConfig(
            executable=self.executable,
            extra_args=list(self.extra_args),
            env=dict(self.env),
            working_directory=self.working_directory,
        )


@dataclass(slots=True)
class ToolsConfig:
    terminal: TerminalToolConfig = field(default_factory=TerminalToolConfig)
    web: WebToolConfig = field(default_factory=WebToolConfig)
    scanner: ScannerToolConfig = field(default_factory=ScannerToolConfig)


@dataclass(slots=True)
class PathsConfig:
    project_root: str = "."
    benchmark_dir: str = "data/benchmarks"
    result_dir: str = "data/results"


@dataclass(slots=True)
class AppConfig:
    workflow: WorkflowConfig = field(default_factory=WorkflowConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    optimization: OptimizationConfig = field(default_factory=OptimizationConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)

    @property
    def providers(self) -> ModelProviderConfig:
        return self.llm.as_legacy_provider_config()

    @property
    def ssh(self) -> SSHConfig:
        return self.runtime.ssh

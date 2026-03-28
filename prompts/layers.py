from __future__ import annotations

from dataclasses import dataclass

from autopt.benchmark.models import BenchmarkItem

from .templates import PromptBundle


SCRATCHPAD_MARKER = "Thought:{agent_scratchpad}"


@dataclass(frozen=True, slots=True)
class PromptLayer:
    scan: str = ""
    inquire: str = ""
    exploit: str = ""
    select: str = ""
    check: str = ""
    optimize: str = ""

    def apply(self, bundle: PromptBundle) -> PromptBundle:
        return bundle.copy(
            scan=_apply_prompt_addition(bundle.scan, self.scan),
            inquire=_apply_prompt_addition(bundle.inquire, self.inquire),
            exploit=_apply_prompt_addition(bundle.exploit, self.exploit),
            select=_apply_prompt_addition(bundle.select, self.select),
            check=_apply_prompt_addition(bundle.check, self.check),
            optimize=_apply_prompt_addition(bundle.optimize, self.optimize),
        )


def _apply_prompt_addition(prompt: str, addition: str) -> str:
    if not addition:
        return prompt
    normalized_addition = addition.strip()
    if not normalized_addition:
        return prompt
    block = f"\n\n{normalized_addition}\n"
    if SCRATCHPAD_MARKER in prompt:
        return prompt.replace(SCRATCHPAD_MARKER, f"{block}{SCRATCHPAD_MARKER}", 1)
    return f"{prompt.rstrip()}{block}"


def build_benchmark_prompt_layer(benchmark: BenchmarkItem | None) -> PromptLayer:
    if benchmark is None:
        return PromptLayer()

    benchmark_lines = [f"Benchmark context: {benchmark.name}"]
    if benchmark.category:
        benchmark_lines.append(f"Category: {benchmark.category}")
    if benchmark.description:
        benchmark_lines.append(f"Description: {benchmark.description}")
    if benchmark.target:
        benchmark_lines.append(f"Target goal: {benchmark.target}")
    if benchmark.references:
        benchmark_lines.append(f"References: {', '.join(benchmark.references)}")
    benchmark_context = "\n".join(benchmark_lines)

    return PromptLayer(
        scan=(
            f"{benchmark_context}\n"
            "Treat the benchmark target goal as the success condition for subsequent steps."
        ),
        inquire=(
            f"{benchmark_context}\n"
            "Prefer evidence and exploitation knowledge directly related to this benchmark."
        ),
        exploit=(
            f"{benchmark_context}\n"
            "Keep the exploitation plan tightly scoped to the benchmark target goal."
        ),
        select=(
            f"{benchmark_context}\n"
            "Prefer vulnerabilities whose exploitation path best matches the benchmark target goal."
        ),
        check=(
            f"{benchmark_context}\n"
            "Only return success if the observed outcome clearly satisfies the benchmark target goal."
        ),
    )

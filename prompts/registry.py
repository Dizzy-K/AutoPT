from __future__ import annotations

from autopt.benchmark.models import BenchmarkItem

from .layers import build_benchmark_prompt_layer
from .templates import DEFAULT_PROMPTS, PromptBundle


PROMPT_BUNDLES: dict[str, PromptBundle] = {
    "default": DEFAULT_PROMPTS,
}


def list_prompt_bundle_names() -> list[str]:
    return sorted(PROMPT_BUNDLES)


def get_prompt_bundle(name: str = "default", *, benchmark: BenchmarkItem | None = None) -> PromptBundle:
    bundle = PROMPT_BUNDLES.get(name)
    if bundle is None:
        raise KeyError(f"Unknown prompt bundle: {name}")
    layered_bundle = build_benchmark_prompt_layer(benchmark).apply(bundle)
    return layered_bundle.copy()

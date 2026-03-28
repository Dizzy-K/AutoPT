from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from autort.config.schema import AppConfig
from autort.models.providers import build_chat_model
from autort.models.registry import ModelSpec

from .templates import DEFAULT_PROMPTS, PromptBundle


SPECIAL_START = "<special>"
SPECIAL_END = "</special>"


def _extract_special_block(text: str) -> str:
    start_index = text.find(SPECIAL_START)
    if start_index == -1:
        return ""
    end_index = text.find(SPECIAL_END, start_index + len(SPECIAL_START))
    if end_index == -1:
        return ""
    return text[start_index + len(SPECIAL_START) : end_index].strip()


def _replace_special_block(text: str, new_content: str) -> str:
    start_index = text.find(SPECIAL_START)
    if start_index == -1:
        return text
    end_index = text.find(SPECIAL_END, start_index + len(SPECIAL_START))
    if end_index == -1:
        return text
    before = text[: start_index + len(SPECIAL_START)]
    after = text[end_index:]
    return f"{before}\n{new_content.strip()}\n{after}"


def collect_stage_history(history: Sequence[str], states: Sequence[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {str(state): [] for state in states}
    for item in history:
        line = str(item)
        lowered = line.lower()
        for state in grouped:
            state_lower = state.lower()
            index = lowered.find(state_lower)
            if index == -1:
                continue
            if lowered[index : index + len(state_lower)] != state_lower:
                continue
            grouped[state].append(line[index + len(state) + 1 :].strip())
    return grouped


class PromptOptimizer:
    def __init__(self, config: AppConfig, llm: Any | None = None) -> None:
        self.config = config
        self._llm = llm

    def optimize(
        self,
        history: Sequence[str],
        *,
        states: Sequence[str] | None = None,
        prompt_bundle: PromptBundle | None = None,
    ) -> PromptBundle:
        target_states = [str(state) for state in (states or self.config.optimization.optimize_states)]
        if not target_states:
            return prompt_bundle or DEFAULT_PROMPTS.copy()

        bundle = prompt_bundle or DEFAULT_PROMPTS.copy()
        grouped_history = collect_stage_history(history, target_states)
        llm = self._llm or self._build_optimizer_model()
        updates: dict[str, str] = {}

        for state in target_states:
            if not hasattr(bundle, state):
                continue
            source_prompt = getattr(bundle, state)
            special_block = _extract_special_block(source_prompt)
            stage_history = grouped_history.get(state, [])
            if not special_block or not stage_history:
                continue

            message = bundle.optimize.format(source=special_block, history=stage_history)
            response = llm.invoke(self._build_messages(message))
            content = str(getattr(response, "content", response))
            updates[state] = _replace_special_block(source_prompt, content)

        if not updates:
            return bundle
        return bundle.copy(**updates)

    @staticmethod
    def _build_messages(message: str) -> list[Any]:
        try:
            from langchain_core.messages import HumanMessage

            return [HumanMessage(content=message)]
        except ImportError:
            return [message]

    def _build_optimizer_model(self) -> Any:
        return build_chat_model(
            ModelSpec(
                alias="prompt_optimizer",
                name=self.config.optimization.model,
                provider="openai",
            ),
            self.config,
        )


def optimize_prompt_bundle(
    history: Sequence[str],
    *,
    config: AppConfig,
    states: Sequence[str] | None = None,
    prompt_bundle: PromptBundle | None = None,
    llm: Any | None = None,
) -> PromptBundle:
    return PromptOptimizer(config=config, llm=llm).optimize(
        history,
        states=states,
        prompt_bundle=prompt_bundle,
    )

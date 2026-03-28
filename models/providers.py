from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from autort.config.schema import AppConfig
from autort.models.registry import ModelSpec


@dataclass(frozen=True, slots=True)
class ProviderPayload:
    provider: str
    model_name: str
    temperature: float
    api_key: str = ""
    api_base: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "api_key": self.api_key,
            "api_base": self.api_base,
        }


def build_provider_payload(provider: str, model_name: str, config: AppConfig) -> ProviderPayload:
    provider_name = provider or config.llm.default_provider
    provider_config = config.llm.get_provider(provider_name)

    if provider_name == "nvidia":
        return ProviderPayload(
            provider=provider_name,
            model_name=model_name,
            temperature=float(provider_config.temperature or 0.0),
            api_key=provider_config.api_key,
        )
    if provider_name == "together":
        return ProviderPayload(
            provider=provider_name,
            model_name=model_name,
            temperature=float(provider_config.temperature or 0.0),
            api_key=provider_config.api_key,
        )
    return ProviderPayload(
        provider="openai",
        model_name=model_name,
        temperature=float(provider_config.temperature or 0.0),
        api_key=provider_config.api_key,
        api_base=provider_config.api_base,
    )


def build_chat_model(model: ModelSpec, config: AppConfig) -> Any:
    payload = build_provider_payload(model.provider, model.name, config)

    if payload.provider == "nvidia":
        try:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA
        except ImportError as exc:
            raise RuntimeError(
                "langchain_nvidia_ai_endpoints is required for NVIDIA-backed models."
            ) from exc
        return ChatNVIDIA(
            temperature=payload.temperature,
            model=payload.model_name,
            api_key=payload.api_key,
        )

    if payload.provider == "together":
        try:
            from langchain_together import ChatTogether
        except ImportError as exc:
            raise RuntimeError(
                "langchain_together is required for Together-backed models."
            ) from exc
        return ChatTogether(
            model=payload.model_name,
            temperature=payload.temperature,
            api_key=payload.api_key,
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "langchain_openai is required for OpenAI-compatible models."
        ) from exc

    return ChatOpenAI(
        temperature=payload.temperature,
        model=payload.model_name,
        openai_api_key=payload.api_key,
        openai_api_base=payload.api_base,
    )

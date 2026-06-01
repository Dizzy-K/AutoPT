from __future__ import annotations

"""Model specification registry and resolution logic."""

from dataclasses import dataclass
from typing import Any


SUPPORTED_PROVIDERS = ("openai", "nvidia", "together")


@dataclass(frozen=True, slots=True)
class ModelSpec:
    alias: str
    name: str
    provider: str = "openai"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "name": self.name,
            "provider": self.provider,
            "notes": self.notes,
        }


def list_supported_providers() -> list[str]:
    return list(SUPPORTED_PROVIDERS)


def build_model_spec(model_name: str, *, provider: str, alias: str | None = None) -> ModelSpec:
    normalized_provider = provider.strip().lower()
    if normalized_provider not in SUPPORTED_PROVIDERS:
        supported = ", ".join(SUPPORTED_PROVIDERS)
        raise ValueError(f"Unsupported model provider `{provider}`. Expected one of: {supported}.")

    normalized_model_name = model_name.strip()
    if not normalized_model_name:
        raise ValueError("Model name cannot be empty.")

    return ModelSpec(
        alias=alias or f"{normalized_provider}:{normalized_model_name}",
        name=normalized_model_name,
        provider=normalized_provider,
    )


def resolve_model(identifier: str, *, default_provider: str = "openai") -> ModelSpec:
    raw_identifier = identifier.strip()
    if not raw_identifier:
        raise ValueError("Model identifier cannot be empty.")

    provider_candidate, separator, model_name = raw_identifier.partition(":")
    if separator and provider_candidate.strip().lower() in SUPPORTED_PROVIDERS:
        return build_model_spec(model_name, provider=provider_candidate)

    return build_model_spec(raw_identifier, provider=default_provider)

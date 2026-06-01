"""Model registry for AutoPT.

Provides model specification, resolution, provider payload construction,
and chat model instantiation for configuring LLM backends.
"""

# Provider layer: build chat models and provider payloads.
from .providers import ProviderPayload, build_chat_model, build_provider_payload
from .registry import ModelSpec, build_model_spec, list_supported_providers, resolve_model

__all__ = [
    "ModelSpec",
    "ProviderPayload",
    "build_model_spec",
    "build_chat_model",
    "build_provider_payload",
    "list_supported_providers",
    "resolve_model",
]

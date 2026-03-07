"""
LLM-Switchboard Provider Adapters
══════════════════════════════════

Pluggable modules for each LLM provider.
Adding a new provider = adding one Python file.
"""

from llm_switchboard.providers.base import BaseProvider, ProviderConfig
from llm_switchboard.providers.anthropic import AnthropicProvider
from llm_switchboard.providers.openai import OpenAIProvider
from llm_switchboard.providers.google import GoogleProvider
from llm_switchboard.providers.mistral import MistralProvider
from llm_switchboard.providers.xai import XAIProvider
from llm_switchboard.providers.cohere import CohereProvider
from llm_switchboard.providers.groq import GroqProvider
from llm_switchboard.providers.together import TogetherProvider
from llm_switchboard.providers.bedrock import BedrockProvider

# Provider class registry — maps provider name to class
PROVIDER_REGISTRY: dict[str, type[BaseProvider]] = {
    "anthropic": AnthropicProvider,
    "openai": OpenAIProvider,
    "google": GoogleProvider,
    "mistral": MistralProvider,
    "xai": XAIProvider,
    "cohere": CohereProvider,
    "groq": GroqProvider,
    "together": TogetherProvider,
    "bedrock": BedrockProvider,
}

__all__ = [
    "BaseProvider",
    "ProviderConfig",
    "PROVIDER_REGISTRY",
    "AnthropicProvider",
    "OpenAIProvider",
    "GoogleProvider",
    "MistralProvider",
    "XAIProvider",
    "CohereProvider",
    "GroqProvider",
    "TogetherProvider",
    "BedrockProvider",
]

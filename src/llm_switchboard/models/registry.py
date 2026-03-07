"""
Model Registry
══════════════

Central catalog of all known models across providers.
Used by the Router for model lookup and capability matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelInfo:
    """Information about a single model."""
    id: str
    name: str
    provider: str
    capabilities: list[str] = field(default_factory=list)
    tier: str = "balanced"
    context_window: int = 100000

    def has_capability(self, cap: str) -> bool:
        return cap in self.capabilities


class ModelRegistry:
    """
    Central registry of all known models.

    Built from providers.yaml configuration at startup.
    """

    def __init__(self):
        self._models: dict[str, ModelInfo] = {}
        self._by_provider: dict[str, list[str]] = {}

    def register(self, model: ModelInfo) -> None:
        """Register a model."""
        self._models[model.id] = model
        self._by_provider.setdefault(model.provider, []).append(model.id)

    def get(self, model_id: str) -> ModelInfo | None:
        """Get a model by ID."""
        return self._models.get(model_id)

    def list_all(self) -> list[ModelInfo]:
        """List all registered models."""
        return list(self._models.values())

    def list_by_provider(self, provider: str) -> list[ModelInfo]:
        """List all models for a provider."""
        ids = self._by_provider.get(provider, [])
        return [self._models[id] for id in ids if id in self._models]

    def find_by_capability(self, *capabilities: str) -> list[ModelInfo]:
        """Find models that have ALL specified capabilities."""
        cap_set = set(capabilities)
        return [
            m for m in self._models.values()
            if cap_set.issubset(set(m.capabilities))
        ]

    def find_by_tier(self, tier: str) -> list[ModelInfo]:
        """Find models of a specific tier."""
        return [m for m in self._models.values() if m.tier == tier]

    @classmethod
    def from_providers_config(cls, providers: dict[str, Any]) -> ModelRegistry:
        """Build a registry from the providers.yaml config dict."""
        registry = cls()
        for provider_name, provider_config in providers.items():
            for model_data in provider_config.get("models", []):
                model = ModelInfo(
                    id=model_data["id"],
                    name=model_data.get("name", model_data["id"]),
                    provider=provider_name,
                    capabilities=model_data.get("capabilities", []),
                    tier=model_data.get("tier", "balanced"),
                    context_window=model_data.get("context_window", 100000),
                )
                registry.register(model)
        return registry

    @property
    def count(self) -> int:
        return len(self._models)

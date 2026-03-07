"""
Base Provider Adapter
═════════════════════

Abstract base class for all provider adapters.
Each provider implements three methods:
  - fetch_status()  → get current status from their page
  - list_models()   → return available models
  - probe(model)    → (optional) send a test request
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx

from llm_switchboard.core.health_engine import ProbeSignal, StatusPageSignal


logger = logging.getLogger("llm_switchboard.providers")


@dataclass
class ProviderConfig:
    """Configuration for a provider adapter."""
    name: str
    status_page_url: str
    status_api_url: str | None
    api_base_url: str | None
    api_key_env: str | None
    models: list[dict]


class BaseProvider(ABC):
    """
    Abstract base class for LLM provider adapters.

    Subclasses must implement fetch_status() and list_models().
    probe() is optional — it costs tokens but catches silent degradation.
    """

    def __init__(self, config: ProviderConfig, api_key: str | None = None):
        self.config = config
        self._api_key = api_key
        self._client = httpx.AsyncClient(timeout=10.0)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def provider_id(self) -> str:
        """Lowercase identifier (e.g., 'anthropic', 'openai')."""
        return self.config.name.lower().replace(" ", "_")

    @abstractmethod
    async def fetch_status(self) -> StatusPageSignal:
        """
        Fetch current status from the provider's status page.

        Returns a StatusPageSignal with the provider's self-reported health.
        This is the primary signal source — it's free and always available.
        """
        ...

    @abstractmethod
    def list_models(self) -> list[dict]:
        """
        Return the list of models this provider offers.

        Each model is a dict with at minimum:
          {"id": "model-id", "name": "Display Name"}
        """
        ...

    async def probe(self, model: str) -> ProbeSignal | None:
        """
        Send a lightweight test request to measure actual health.

        Optional — costs tokens but catches silent degradation that
        status pages miss. Returns None if probing is not supported
        or not configured (no API key).
        """
        return None  # Default: no probing

    async def close(self):
        """Clean up HTTP client."""
        await self._client.aclose()

    # ── Shared Utilities ─────────────────────────────────────────

    async def _fetch_statuspage_json(self, url: str) -> dict:
        """
        Fetch and parse an Atlassian Statuspage JSON API response.

        Most major providers use Atlassian Statuspage, which exposes
        a JSON API at /api/v2/summary.json.
        """
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as e:
            logger.warning(f"Failed to fetch status page for {self.name}: {e}")
            return {}
        except Exception as e:
            logger.warning(f"Unexpected error fetching status for {self.name}: {e}")
            return {}

    def _parse_statuspage_indicator(self, data: dict) -> str:
        """
        Parse the indicator from an Atlassian Statuspage summary response.

        The status.indicator field contains:
          none, minor, major, critical, maintenance
        """
        status = data.get("status", {})
        indicator = status.get("indicator", "unknown")

        # Map Statuspage indicators to our status vocabulary
        mapping = {
            "none": "operational",
            "minor": "minor_outage",
            "major": "major_outage",
            "critical": "major_outage",
            "maintenance": "maintenance",
        }
        return mapping.get(indicator, indicator)

    def _parse_statuspage_components(self, data: dict) -> list[dict]:
        """Parse component statuses from Statuspage response."""
        components = data.get("components", [])
        return [
            {
                "name": c.get("name", "unknown"),
                "status": c.get("status", "unknown"),
                "description": c.get("description", ""),
            }
            for c in components
            if c.get("name") and c.get("group", True) is not False
        ]

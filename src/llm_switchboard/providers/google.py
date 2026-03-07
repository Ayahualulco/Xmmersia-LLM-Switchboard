"""
Google Provider Adapter
═══════════════════════

Fetches health from Google Cloud Status and optionally probes Gemini API.
"""

from __future__ import annotations

import logging
import time

from llm_switchboard.core.health_engine import ProbeSignal, StatusPageSignal
from llm_switchboard.providers.base import BaseProvider


logger = logging.getLogger("llm_switchboard.providers.google")


class GoogleProvider(BaseProvider):
    """Adapter for Google (Gemini models)."""

    async def fetch_status(self) -> StatusPageSignal:
        """Fetch status from Google Cloud Status."""
        url = self.config.status_api_url
        if not url:
            return StatusPageSignal(
                provider="google",
                status="unknown",
                description="No status API URL configured",
            )

        # Google uses a different format than Atlassian Statuspage
        # Try the standard format first, fall back gracefully
        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(
                provider="google",
                status="unknown",
                description="Failed to fetch status page",
            )

        # Google Cloud status may use a different schema
        # Attempt standard Statuspage parsing first
        if "status" in data:
            status = self._parse_statuspage_indicator(data)
        else:
            # Fallback: assume operational if page loads
            status = "operational"

        return StatusPageSignal(
            provider="google",
            status=status,
            description="Google AI Platform status",
            raw_data=data,
        )

    def list_models(self) -> list[dict]:
        """Return Google's model catalog."""
        return self.config.models

    async def probe(self, model: str) -> ProbeSignal | None:
        """Send a lightweight test request to Gemini API."""
        if not self._api_key:
            return None

        start = time.time()
        try:
            # Gemini API endpoint format
            url = (
                f"{self.config.api_base_url}/v1beta/models/{model}"
                f":generateContent?key={self._api_key}"
            )
            response = await self._client.post(
                url,
                json={
                    "contents": [
                        {"parts": [{"text": "Say 'ok' and nothing else."}]}
                    ],
                    "generationConfig": {"maxOutputTokens": 5},
                },
                timeout=15.0,
            )
            latency_ms = (time.time() - start) * 1000

            return ProbeSignal(
                provider="google",
                model=model,
                success=response.status_code == 200,
                latency_ms=latency_ms,
                error=(
                    f"HTTP {response.status_code}" if response.status_code != 200 else None
                ),
            )

        except Exception as e:
            latency_ms = (time.time() - start) * 1000
            return ProbeSignal(
                provider="google",
                model=model,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )

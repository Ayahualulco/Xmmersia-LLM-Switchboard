"""
xAI Provider Adapter
════════════════════

Fetches health from status.x.ai and optionally probes the API.

xAI's API is OpenAI-compatible (same /v1/chat/completions endpoint,
same auth pattern), so probing follows the OpenAI adapter pattern
with xAI-specific base URL and headers.

Status page: https://status.x.ai/
  - Shows live monitoring data for API (regional endpoints),
    Console, Docs, and Grok-in-X.
  - Does NOT use standard Atlassian Statuspage JSON format.
  - We attempt the standard parse first, then fall back to
    treating a reachable page as "operational".
"""

from __future__ import annotations

import logging
import time

from llm_switchboard.core.health_engine import ProbeSignal, StatusPageSignal
from llm_switchboard.providers.base import BaseProvider


logger = logging.getLogger("llm_switchboard.providers.xai")


class XAIProvider(BaseProvider):
    """Adapter for xAI (Grok models)."""

    async def fetch_status(self) -> StatusPageSignal:
        """
        Fetch status from status.x.ai.

        xAI's status page uses a custom format (not standard Atlassian
        Statuspage). We attempt standard parsing first; if the JSON
        structure differs, we fall back to treating a reachable page
        as operational and an unreachable one as unknown.
        """
        url = self.config.status_api_url
        if not url:
            # No structured API — try fetching the status page directly
            # to at least confirm it's reachable
            try:
                response = await self._client.get(
                    self.config.status_page_url,
                    timeout=10.0,
                )
                if response.status_code == 200:
                    return StatusPageSignal(
                        provider="xai",
                        status="operational",
                        description="Status page reachable (no structured API available)",
                    )
                else:
                    return StatusPageSignal(
                        provider="xai",
                        status="unknown",
                        description=f"Status page returned HTTP {response.status_code}",
                    )
            except Exception as e:
                logger.warning(f"Failed to reach xAI status page: {e}")
                return StatusPageSignal(
                    provider="xai",
                    status="unknown",
                    description=f"Status page unreachable: {e}",
                )

        # If a structured API URL is configured, try standard parsing
        data = await self._fetch_statuspage_json(url)
        if not data:
            return StatusPageSignal(
                provider="xai",
                status="unknown",
                description="Failed to fetch structured status data",
            )

        status = self._parse_statuspage_indicator(data)
        components = self._parse_statuspage_components(data)
        affected = [
            c["name"] for c in components
            if c.get("status") != "operational"
        ]

        return StatusPageSignal(
            provider="xai",
            status=status,
            description=data.get("status", {}).get("description", ""),
            affected_components=affected,
            raw_data=data,
        )

    def list_models(self) -> list[dict]:
        """Return xAI's model catalog."""
        return self.config.models

    async def probe(self, model: str) -> ProbeSignal | None:
        """
        Send a lightweight test request to xAI's API.

        xAI's API is OpenAI-compatible: same /v1/chat/completions
        endpoint, Bearer token auth, identical request format.
        Requires XAI_API_KEY to be configured.
        """
        if not self._api_key:
            return None

        start = time.time()
        try:
            response = await self._client.post(
                f"{self.config.api_base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 5,
                    "messages": [
                        {"role": "user", "content": "Say 'ok' and nothing else."}
                    ],
                },
                timeout=15.0,
            )
            latency_ms = (time.time() - start) * 1000

            return ProbeSignal(
                provider="xai",
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
                provider="xai",
                model=model,
                success=False,
                latency_ms=latency_ms,
                error=str(e),
            )

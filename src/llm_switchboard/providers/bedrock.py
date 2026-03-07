"""
AWS Bedrock Provider Adapter
════════════════════════════

Bedrock is different — it uses AWS health dashboards and boto3.
This adapter provides a basic structure for future implementation.
"""

from __future__ import annotations

from llm_switchboard.core.health_engine import StatusPageSignal
from llm_switchboard.providers.base import BaseProvider


class BedrockProvider(BaseProvider):
    """Adapter for AWS Bedrock (multi-provider hosting)."""

    async def fetch_status(self) -> StatusPageSignal:
        # AWS health uses a very different format (not Atlassian Statuspage)
        # For now, return unknown — full implementation will use boto3 health checks
        return StatusPageSignal(
            provider="bedrock",
            status="unknown",
            description="AWS Bedrock health check requires boto3 (not yet implemented)",
        )

    def list_models(self) -> list[dict]:
        return self.config.models

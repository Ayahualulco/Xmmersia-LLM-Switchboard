"""
LLM-Switchboard
═══════════════

Proactive LLM health intelligence, routing, and provenance stamping.

    The operator who watches the lines and connects you to the right one.

Usage:
    from llm_switchboard import Switchboard

    sb = Switchboard()

    # 1. Check — what's the state of the world?
    health = sb.check("claude-opus-4-6")

    # 2. Route — what should I do about it?
    result = sb.route(preferred_model="claude-opus-4-6", policy=CAREFUL)

    # 3. Stamp — record what happened
    stamp = sb.stamp(
        model_requested="claude-opus-4-6",
        model_used=result.routed_to,
        action_taken=result.action,
        reason=result.reason,
    )

Built by Xmmersia — because every learner deserves reliable AI,
and every builder deserves honest tools.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml

from llm_switchboard.config import defaults
from llm_switchboard.core.health_engine import (
    HealthAssessment,
    HealthEngine,
    HealthStatus,
    StatusPageSignal,
)
from llm_switchboard.core.router import Router, RoutingResult
from llm_switchboard.core.stamper import ConfidenceFlag, ProvenanceStamp, Stamper
from llm_switchboard.models.registry import ModelRegistry
from llm_switchboard.policies import CAREFUL, CRITICAL, FAST, get_policy


logger = logging.getLogger("llm_switchboard")


class Switchboard:
    """
    Main entry point for LLM-Switchboard.

    Provides three operations:
        check()  — Pre-flight health check for a model
        route()  — Intelligent routing with policy-based decisions
        stamp()  — Provenance stamp generation for audit trails

    Advisory, not invasive. Doesn't sit in your request path.
    Doesn't add latency. You ask it "what's the state of the world?"
    and it tells you. What you do with that information is up to your policy.
    """

    VERSION = "1.0.0"

    def __init__(
        self,
        config_path: str | Path | None = None,
        providers_config: dict | None = None,
        cache_ttl: float = defaults.DEFAULT_CACHE_TTL,
    ):
        """
        Initialize Switchboard.

        Args:
            config_path: Path to providers.yaml (uses bundled default if None).
            providers_config: Direct providers config dict (overrides config_path).
            cache_ttl: How long to cache health checks (seconds).
        """
        # Load provider configuration
        if providers_config:
            self._providers = providers_config
        else:
            config_file = Path(config_path) if config_path else defaults.PROVIDERS_YAML
            self._providers = self._load_config(config_file)

        # Initialize components
        self._engine = HealthEngine(
            providers=self._providers,
            cache_ttl=cache_ttl,
        )
        self._router = Router(
            health_engine=self._engine,
            providers=self._providers,
        )
        self._stamper = Stamper()
        self._registry = ModelRegistry.from_providers_config(self._providers)

        logger.info(
            f"Switchboard v{self.VERSION} initialized with "
            f"{len(self._providers)} providers, "
            f"{self._registry.count} models"
        )

    # ── Public API ───────────────────────────────────────────────

    def check(self, model: str) -> dict:
        """
        Pre-flight health check for a model.

        Returns a dict with the model's health status, confidence,
        latency, recommendation, and alternatives.

        This is the "Watch" operation — know before you call.
        """
        assessment = self._engine.assess(model)

        # Find alternatives if not healthy
        alternatives = []
        if assessment.status != HealthStatus.HEALTHY:
            alternatives = self._find_alternatives(model)

        result = assessment.to_dict()
        result["alternatives"] = alternatives
        return result

    def route(
        self,
        preferred_model: str = "claude-opus-4-6",
        policy: dict | str = "careful",
        prompt: str | None = None,
    ) -> RoutingResult:
        """
        Route a request based on health and policy.

        This is the "Act" operation — decide what to do.

        Args:
            preferred_model: The model you want to use.
            policy: A policy dict, or name of a built-in policy
                    ("fast", "careful", "critical").
            prompt: Optional task description (for logging only).

        Returns:
            RoutingResult with routing decision and provenance data.
        """
        # Resolve policy name to dict
        if isinstance(policy, str):
            policy = get_policy(policy)

        result = self._router.route(
            preferred_model=preferred_model,
            policy=policy,
            prompt=prompt,
        )

        # Attach provenance data to the result
        result.provenance = self.stamp(
            model_requested=preferred_model,
            model_used=result.routed_to,
            action_taken=result.action,
            reason=result.reason,
        ).to_dict()

        return result

    def stamp(
        self,
        model_requested: str,
        model_used: str,
        action_taken: str,
        reason: str,
        metadata: dict | None = None,
    ) -> ProvenanceStamp:
        """
        Generate a provenance stamp.

        This is the "Remember" operation — keep an honest record.

        Attach the returned stamp to any output (graded exam, lesson plan,
        report, etc.) so you always know the conditions under which it
        was generated.
        """
        # Gather current provider statuses
        provider_statuses = self._current_provider_statuses()

        return self._stamper.stamp(
            model_requested=model_requested,
            model_used=model_used,
            action_taken=action_taken,
            reason=reason,
            provider_statuses=provider_statuses,
            metadata=metadata,
        )

    def get_stamp(self, stamp_id: str) -> dict | None:
        """Retrieve a stored provenance stamp."""
        stamp = self._stamper.get_stamp(stamp_id)
        return stamp.to_dict() if stamp else None

    def status(self) -> dict:
        """
        Get Switchboard's own status — providers, models, health summary.
        """
        assessments = self._engine.get_all_assessments()

        # Count by status
        status_counts = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}
        for a in assessments.values():
            status_counts[a.status.value] = status_counts.get(a.status.value, 0) + 1

        return {
            "switchboard_version": self.VERSION,
            "providers": len(self._providers),
            "models": self._registry.count,
            "stamps_stored": self._stamper.stamp_count,
            "health_summary": status_counts,
            "provider_list": list(self._providers.keys()),
        }

    def update_status(self, provider: str, signal: StatusPageSignal) -> None:
        """
        Manually update a provider's status signal.

        Useful for integrating with external monitoring systems
        or for testing.
        """
        self._engine.update_status_signal(signal)

    # ── Provider & Model Info ────────────────────────────────────

    def list_providers(self) -> list[str]:
        """List all supported provider names."""
        return list(self._providers.keys())

    def list_models(self, provider: str | None = None) -> list[dict]:
        """List models, optionally filtered by provider."""
        if provider:
            models = self._registry.list_by_provider(provider)
        else:
            models = self._registry.list_all()

        return [
            {
                "id": m.id,
                "name": m.name,
                "provider": m.provider,
                "capabilities": m.capabilities,
                "tier": m.tier,
            }
            for m in models
        ]

    # ── Private Methods ──────────────────────────────────────────

    def _load_config(self, path: Path) -> dict:
        """Load and parse providers.yaml."""
        try:
            with open(path) as f:
                config = yaml.safe_load(f)
            return config.get("providers", config)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {path}. Using empty config.")
            return {}
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def _find_alternatives(self, model: str, limit: int = 3) -> list[dict]:
        """Find alternative models ranked by equivalence."""
        model_info = self._registry.get(model)
        if not model_info:
            return []

        from llm_switchboard.models.equivalence import rank_alternatives

        all_models = self._registry.list_all()
        ranked = rank_alternatives(model_info, all_models)

        alternatives = []
        for alt_model, score in ranked[:limit]:
            alt_assessment = self._engine.assess(alt_model.id)
            alternatives.append({
                "model": alt_model.id,
                "status": alt_assessment.status.value,
                "match_score": score,
            })

        return alternatives

    def _current_provider_statuses(self) -> dict[str, str]:
        """Get current status for all providers (from cache)."""
        statuses = {}
        for provider_name in self._providers:
            # Check if we have a cached status signal
            signal = self._engine._status_signals.get(provider_name)
            if signal:
                statuses[provider_name] = signal.status
            else:
                statuses[provider_name] = "unknown"
        return statuses

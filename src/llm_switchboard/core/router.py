"""
Router
══════

Takes a health assessment + a configurable policy and decides:
proceed, reroute, or stop.

Includes model matching that knows which models are reasonable
substitutes for each other based on capabilities and tier.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from llm_switchboard.core.health_engine import (
    HealthAssessment,
    HealthEngine,
    HealthStatus,
    Recommendation,
)


logger = logging.getLogger("llm_switchboard.router")


_VALID_TRUST_TIERS = {"trusted", "watched", "untrusted"}


# ── Routing Result ───────────────────────────────────────────────

@dataclass
class RoutingResult:
    """The result of a routing decision."""
    routed_to: str                          # The model to actually use
    reason: str                             # Human-readable explanation
    action: str                             # "proceed" | "rerouted" | "warned" | "stopped"
    primary_assessment: HealthAssessment | None = None
    alternatives_checked: list[str] = field(default_factory=list)
    provenance: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "routed_to": self.routed_to,
            "reason": self.reason,
            "action": self.action,
            "primary_assessment": (
                self.primary_assessment.to_dict() if self.primary_assessment else None
            ),
            "alternatives_checked": self.alternatives_checked,
            "provenance": self.provenance,
        }


# ── Router ───────────────────────────────────────────────────────

class Router:
    """
    Policy-aware routing engine.

    Given a preferred model and a policy, decides whether to
    proceed, reroute to an alternative, or stop and alert.
    """

    def __init__(self, health_engine: HealthEngine, providers: dict[str, Any]):
        self._engine = health_engine
        self._providers = providers

    def route(
        self,
        preferred_model: str,
        policy: dict,
        prompt: str | None = None,
    ) -> RoutingResult:
        """
        Route a request based on health and policy.

        Args:
            preferred_model: The model the caller wants to use.
            policy: Routing policy dict with keys like criticality,
                    on_degraded, on_down, acceptable_models, min_status.
            prompt: Optional task description (for logging, not sent anywhere).

        Returns:
            RoutingResult with the routing decision.
        """
        # ── Trust gate: evaluated before health. Honesty before uptime. ──
        trust_result = self._check_trust_gate(preferred_model, policy)
        if trust_result is not None:
            return trust_result

        # Assess primary model
        assessment = self._engine.assess(preferred_model)

        # Check if primary is acceptable under the policy
        min_status = policy.get("min_status", "degraded")
        on_degraded = policy.get("on_degraded", "warn")
        on_down = policy.get("on_down", "reroute")
        criticality = policy.get("criticality", "medium")

        logger.info(
            f"Routing check: model={preferred_model}, "
            f"status={assessment.status.value}, "
            f"criticality={criticality}"
        )

        # ── Decision Logic ───────────────────────────────────────

        if assessment.status == HealthStatus.HEALTHY:
            return RoutingResult(
                routed_to=preferred_model,
                reason="Primary model is healthy",
                action="proceed",
                primary_assessment=assessment,
            )

        if assessment.status == HealthStatus.DEGRADED:
            return self._handle_degraded(
                preferred_model, assessment, policy, on_degraded
            )

        if assessment.status == HealthStatus.DOWN:
            return self._handle_down(
                preferred_model, assessment, policy, on_down
            )

        # Unknown status — treat cautiously
        if on_degraded == "stop":
            return RoutingResult(
                routed_to=preferred_model,
                reason=f"Primary model status unknown; stopping per {criticality}-criticality policy",
                action="stopped",
                primary_assessment=assessment,
            )

        return RoutingResult(
            routed_to=preferred_model,
            reason="Primary model status unknown; proceeding with caution",
            action="warned",
            primary_assessment=assessment,
        )

    # ── Status Handlers ──────────────────────────────────────────

    def _handle_degraded(
        self,
        preferred: str,
        assessment: HealthAssessment,
        policy: dict,
        action: str,
    ) -> RoutingResult:
        """Handle a degraded primary model."""
        if action == "proceed":
            return RoutingResult(
                routed_to=preferred,
                reason="Primary model degraded; proceeding per policy",
                action="proceed",
                primary_assessment=assessment,
            )

        if action == "warn":
            return RoutingResult(
                routed_to=preferred,
                reason="Primary model degraded; proceeding with warning",
                action="warned",
                primary_assessment=assessment,
            )

        if action == "reroute":
            return self._find_alternative(preferred, assessment, policy)

        if action == "stop":
            return RoutingResult(
                routed_to=preferred,
                reason="Primary model degraded; stopped per policy (high criticality)",
                action="stopped",
                primary_assessment=assessment,
            )

        # Fallback: warn
        return RoutingResult(
            routed_to=preferred,
            reason=f"Primary model degraded; unknown action '{action}', warning",
            action="warned",
            primary_assessment=assessment,
        )

    def _handle_down(
        self,
        preferred: str,
        assessment: HealthAssessment,
        policy: dict,
        action: str,
    ) -> RoutingResult:
        """Handle a down primary model."""
        if action == "reroute":
            return self._find_alternative(preferred, assessment, policy)

        if action == "stop":
            return RoutingResult(
                routed_to=preferred,
                reason="Primary model down; stopped per policy",
                action="stopped",
                primary_assessment=assessment,
            )

        if action == "queue":
            return RoutingResult(
                routed_to=preferred,
                reason="Primary model down; request queued for retry",
                action="stopped",  # caller should queue
                primary_assessment=assessment,
            )

        # Fallback: try to reroute
        return self._find_alternative(preferred, assessment, policy)

    # ── Alternative Finding ──────────────────────────────────────

    def _find_alternative(
        self,
        preferred: str,
        primary_assessment: HealthAssessment,
        policy: dict,
        refusal_reason: str | None = None,
    ) -> RoutingResult:
        """Find the best healthy, trust-eligible alternative model."""
        acceptable = policy.get("acceptable_models", [])
        min_status = policy.get("min_status", "healthy")
        max_latency = policy.get("max_latency_ms", None)

        # Build candidate list: explicit acceptable_models, or all known models
        candidates = acceptable if acceptable else self._all_model_ids()

        # Remove the primary (it's already failed)
        candidates = [m for m in candidates if m != preferred]

        checked = []
        for candidate in candidates:
            if not self._trust_allowed(candidate, policy):
                continue  # not health-checked; excluded on trust, not availability

            candidate_assessment = self._engine.assess(candidate)
            checked.append(candidate)

            # Check health meets minimum
            if not self._meets_min_status(candidate_assessment.status, min_status):
                continue

            # Check latency if specified
            if max_latency and candidate_assessment.latency_ms:
                if candidate_assessment.latency_ms > max_latency:
                    continue

            # Found a viable alternative
            match_score = self._match_score(preferred, candidate)
            logger.info(
                f"Rerouting {preferred} → {candidate} "
                f"(match={match_score:.2f}, status={candidate_assessment.status.value})"
            )

            reason = (
                f"{refusal_reason}; rerouted to {candidate} (match score: {match_score:.2f})"
                if refusal_reason else
                f"Primary model {preferred} is {primary_assessment.status.value}; "
                f"rerouted to {candidate} (match score: {match_score:.2f})"
            )
            return RoutingResult(
                routed_to=candidate,
                reason=reason,
                action="rerouted",
                primary_assessment=primary_assessment,
                alternatives_checked=checked,
            )

        # No alternative found
        reason = (
            f"{refusal_reason}; no trust-eligible healthy alternative found "
            f"among {len(checked)} candidates"
            if refusal_reason else
            f"Primary model {preferred} is {primary_assessment.status.value}; "
            f"no healthy alternative found among {len(checked)} candidates"
        )
        return RoutingResult(
            routed_to=preferred,
            reason=reason,
            action="stopped",
            primary_assessment=primary_assessment,
            alternatives_checked=checked,
        )

    # ── Trust Tier Gate ──────────────────────────────────────────

    def _trust_tier(self, model_id: str) -> str:
        """Look up a model's trust tier from providers config. Unset → 'trusted'."""
        info = self._model_info(model_id)
        return (info or {}).get("trust_tier", "trusted")

    def _trust_allowed(self, model_id: str, policy: dict) -> bool:
        """
        Whether this model may be used at all under this policy's criticality,
        independent of health. Evaluated before — and orthogonal to — the
        health-based decision. 'Honesty before uptime.'
        Gate table: L'Atelier llm-switchboard §06.
        """
        tier = self._trust_tier(model_id)
        if tier not in _VALID_TRUST_TIERS:
            logger.warning(
                f"Unknown trust_tier '{tier}' for {model_id}; treating as untrusted"
            )
            tier = "untrusted"

        if tier == "trusted":
            return True

        criticality = policy.get("criticality", "medium")

        if tier == "watched":
            return criticality != "critical"

        # untrusted: refused for CAREFUL/CRITICAL outright; refused for FAST
        # only when the call is learner-facing (default: assume it is).
        if criticality in ("critical", "medium"):
            return False
        return not policy.get("learner_facing", True)

    def _check_trust_gate(self, preferred: str, policy: dict) -> RoutingResult | None:
        """Trust gate, run before the health/operational matrix. None = proceed to health check."""
        if self._trust_allowed(preferred, policy):
            return None

        tier = self._trust_tier(preferred)
        criticality = policy.get("criticality", "medium")
        logger.warning(
            f"Trust gate: {preferred} (trust_tier={tier}) refused under "
            f"criticality={criticality} policy"
        )
        assessment = self._engine.assess(preferred)
        return self._find_alternative(
            preferred,
            assessment,
            policy,
            refusal_reason=(
                f"Primary model {preferred} has trust_tier={tier}, refused "
                f"under criticality={criticality} policy"
            ),
        )

    def _meets_min_status(self, status: HealthStatus, min_status: str) -> bool:
        """Check if a health status meets the minimum requirement."""
        hierarchy = {
            "healthy": [HealthStatus.HEALTHY],
            "degraded": [HealthStatus.HEALTHY, HealthStatus.DEGRADED],
        }
        acceptable = hierarchy.get(min_status, [HealthStatus.HEALTHY])
        return status in acceptable

    def _match_score(self, original: str, candidate: str) -> float:
        """
        Score how well a candidate model substitutes for the original.

        Considers capability overlap and tier compatibility.
        Returns 0-1 where 1 = perfect match.
        """
        original_info = self._model_info(original)
        candidate_info = self._model_info(candidate)

        if not original_info or not candidate_info:
            return 0.5  # Unknown models get a neutral score

        # Capability overlap
        orig_caps = set(original_info.get("capabilities", []))
        cand_caps = set(candidate_info.get("capabilities", []))

        if not orig_caps:
            cap_score = 0.5
        else:
            overlap = len(orig_caps & cand_caps)
            cap_score = overlap / len(orig_caps)

        # Tier compatibility
        orig_tier = original_info.get("tier", "balanced")
        cand_tier = candidate_info.get("tier", "balanced")
        tier_score = 1.0 if orig_tier == cand_tier else 0.7

        # Context window compatibility
        orig_ctx = original_info.get("context_window", 100000)
        cand_ctx = candidate_info.get("context_window", 100000)
        ctx_score = 1.0 if cand_ctx >= orig_ctx else cand_ctx / orig_ctx

        # Weighted combination
        return (cap_score * 0.5) + (tier_score * 0.3) + (ctx_score * 0.2)

    def _model_info(self, model_id: str) -> dict | None:
        """Get model info from providers config."""
        for provider_config in self._providers.values():
            for model_info in provider_config.get("models", []):
                if model_info["id"] == model_id:
                    return model_info
        return None

    def _all_model_ids(self) -> list[str]:
        """Get all known model IDs."""
        models = []
        for provider_config in self._providers.values():
            for model_info in provider_config.get("models", []):
                models.append(model_info["id"])
        return models

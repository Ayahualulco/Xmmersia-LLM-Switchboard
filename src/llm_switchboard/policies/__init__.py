"""
Built-in Policy Presets
═══════════════════════

Three opinionated policies for common scenarios.
Use these directly or as starting points for custom policies.

    FAST     — reroute silently, never stop. Good for chatbots, summaries.
    CAREFUL  — reroute with warnings, stop if nothing healthy. Good for content generation.
    CRITICAL — stop and alert human if primary is degraded. Good for grading, legal, medical.
"""

from llm_switchboard.policies.engine import evaluate_policy, validate_policy

# ── FAST ─────────────────────────────────────────────────────────
# Reroute silently, never stop. Maximize availability.
# Good for: chatbots, summaries, quick lookups, internal tools

FAST: dict = {
    "priority": "speed",
    "criticality": "low",
    "on_degraded": "reroute",
    "on_down": "reroute",
    "min_status": "degraded",    # Accept degraded models as fallback
    "acceptable_models": [],     # Empty = try all known models
}


# ── CAREFUL ──────────────────────────────────────────────────────
# Reroute with warnings, stop if nothing is healthy.
# Good for: content generation, code writing, lesson plans

CAREFUL: dict = {
    "priority": "quality",
    "criticality": "medium",
    "on_degraded": "warn",
    "on_down": "reroute",
    "min_status": "healthy",     # Only route to healthy models
    "acceptable_models": [],     # Empty = try all known models
}


# ── CRITICAL ─────────────────────────────────────────────────────
# Stop and alert human if anything is wrong. Trust nothing degraded.
# Good for: grading, legal docs, medical info, financial analysis

CRITICAL: dict = {
    "priority": "quality",
    "criticality": "critical",
    "on_degraded": "stop",
    "on_down": "stop",
    "min_status": "healthy",     # Only healthy models allowed
    "acceptable_models": [],     # Must be explicitly set by caller
}


# ── Convenience function ─────────────────────────────────────────

def get_policy(name: str) -> dict:
    """Get a built-in policy by name."""
    policies = {
        "fast": FAST,
        "careful": CAREFUL,
        "critical": CRITICAL,
    }
    policy = policies.get(name.lower())
    if policy is None:
        raise ValueError(
            f"Unknown policy '{name}'. Available: {list(policies.keys())}"
        )
    return policy.copy()  # Return a copy so callers can modify


__all__ = [
    "FAST",
    "CAREFUL",
    "CRITICAL",
    "get_policy",
    "evaluate_policy",
    "validate_policy",
]

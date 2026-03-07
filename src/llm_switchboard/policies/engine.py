"""
Policy Engine
═════════════

Evaluates routing policies against health assessments.
Different tasks have different stakes — a chatbot can tolerate rerouting,
a graded exam needs a human in the loop.
"""

from __future__ import annotations

from typing import Any

from llm_switchboard.core.health_engine import HealthAssessment, HealthStatus


def evaluate_policy(
    assessment: HealthAssessment,
    policy: dict[str, Any],
) -> dict[str, Any]:
    """
    Evaluate a policy against a health assessment.

    Returns a decision dict:
        {
            "action": "proceed" | "warn" | "reroute" | "stop",
            "reason": "human-readable explanation",
            "should_notify": bool,
            "notification_target": str | None,
        }
    """
    status = assessment.status
    criticality = policy.get("criticality", "medium")
    min_status = policy.get("min_status", "healthy")

    # Determine the policy action for the current status
    if status == HealthStatus.HEALTHY:
        return {
            "action": "proceed",
            "reason": "Model is healthy",
            "should_notify": False,
            "notification_target": None,
        }

    if status == HealthStatus.DEGRADED:
        action = policy.get("on_degraded", "warn")
    elif status == HealthStatus.DOWN:
        action = policy.get("on_down", "reroute")
    else:
        # Unknown — treat as degraded
        action = policy.get("on_degraded", "warn")

    # Check notification
    notify_target = policy.get("notify", None)
    should_notify = notify_target is not None and action in ("reroute", "stop")

    return {
        "action": action,
        "reason": f"Model is {status.value}; policy ({criticality}) says: {action}",
        "should_notify": should_notify,
        "notification_target": notify_target,
    }


def validate_policy(policy: dict[str, Any]) -> list[str]:
    """
    Validate a policy dict. Returns list of error messages (empty = valid).
    """
    errors = []

    valid_criticalities = {"low", "medium", "high", "critical"}
    if policy.get("criticality") and policy["criticality"] not in valid_criticalities:
        errors.append(
            f"Invalid criticality '{policy['criticality']}'; "
            f"must be one of {valid_criticalities}"
        )

    valid_actions = {"proceed", "warn", "reroute", "stop", "queue"}
    for key in ("on_degraded", "on_down"):
        if policy.get(key) and policy[key] not in valid_actions:
            errors.append(
                f"Invalid {key} action '{policy[key]}'; "
                f"must be one of {valid_actions}"
            )

    valid_statuses = {"healthy", "degraded"}
    if policy.get("min_status") and policy["min_status"] not in valid_statuses:
        errors.append(
            f"Invalid min_status '{policy['min_status']}'; "
            f"must be one of {valid_statuses}"
        )

    if policy.get("max_latency_ms") and not isinstance(policy["max_latency_ms"], (int, float)):
        errors.append("max_latency_ms must be a number")

    if policy.get("acceptable_models") and not isinstance(policy["acceptable_models"], list):
        errors.append("acceptable_models must be a list")

    return errors

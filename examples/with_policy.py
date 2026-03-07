"""
Policy-Based Routing Example
═════════════════════════════

Different tasks have different stakes. Use policies to control
how Switchboard handles degradation.
"""

from llm_switchboard import Switchboard
from llm_switchboard.policies import FAST, CAREFUL, CRITICAL

sb = Switchboard()


# ── Example 1: Quick chatbot response (FAST) ────────────────────
# Low stakes — reroute silently if needed, never block the user.

result = sb.route(
    preferred_model="claude-opus-4-6",
    policy="fast",
    prompt="Summarize this article",
)
print(f"[FAST] Routed to: {result.routed_to} ({result.action})")


# ── Example 2: Lesson plan generation (CAREFUL) ─────────────────
# Medium stakes — warn if degraded, reroute if down.

result = sb.route(
    preferred_model="claude-opus-4-6",
    policy="careful",
    prompt="Generate a lesson plan for derivatives",
)
print(f"[CAREFUL] Routed to: {result.routed_to} ({result.action})")
if result.action == "warned":
    print(f"  ⚠ Warning: {result.reason}")


# ── Example 3: Grading a student exam (CRITICAL) ────────────────
# High stakes — stop if anything is wrong. A human needs to review.

result = sb.route(
    preferred_model="claude-opus-4-6",
    policy=CRITICAL,
    prompt="Grade this calculus midterm",
)
print(f"[CRITICAL] Routed to: {result.routed_to} ({result.action})")
if result.action == "stopped":
    print(f"  ✗ STOPPED: {result.reason}")
    print(f"  → A human should review this task")


# ── Example 4: Custom policy ────────────────────────────────────
# Fine-grained control for specific requirements.

custom_policy = {
    "priority": "quality",
    "criticality": "high",
    "on_degraded": "reroute",
    "on_down": "stop",
    "acceptable_models": ["claude-opus-4-6", "gpt-4o", "gemini-2.0-pro"],
    "min_status": "healthy",
    "max_latency_ms": 5000,
}

result = sb.route(
    preferred_model="claude-opus-4-6",
    policy=custom_policy,
    prompt="Write a formal assessment report",
)
print(f"[CUSTOM] Routed to: {result.routed_to} ({result.action})")

# Every result includes a provenance stamp
stamp = result.provenance
print(f"\nProvenance stamp: {stamp.get('stamp_id')}")
print(f"  Confidence: {stamp.get('confidence_flag')}")

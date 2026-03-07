"""
Model Equivalence Scoring
═════════════════════════

Determines how well one model can substitute for another.
Goes beyond simple "same tier" matching to consider capability overlap,
context window compatibility, and provider diversity.
"""

from __future__ import annotations

from llm_switchboard.models.registry import ModelInfo, ModelRegistry


def equivalence_score(
    original: ModelInfo,
    candidate: ModelInfo,
    registry: ModelRegistry | None = None,
) -> float:
    """
    Score how well a candidate model can substitute for the original.

    Returns 0.0 (terrible substitute) to 1.0 (perfect match).

    Scoring components:
        - Capability overlap (50%): Does the candidate have the same capabilities?
        - Tier compatibility (30%): Is it the same class of model?
        - Context window (20%): Can it handle the same input sizes?
    """
    cap_score = _capability_score(original, candidate)
    tier_score = _tier_score(original, candidate)
    ctx_score = _context_score(original, candidate)

    return round(
        (cap_score * 0.50) + (tier_score * 0.30) + (ctx_score * 0.20),
        3,
    )


def rank_alternatives(
    original: ModelInfo,
    candidates: list[ModelInfo],
    registry: ModelRegistry | None = None,
) -> list[tuple[ModelInfo, float]]:
    """
    Rank candidate models by how well they substitute for the original.

    Returns list of (model, score) sorted by score descending.
    Excludes the original model itself.
    """
    scored = []
    for candidate in candidates:
        if candidate.id == original.id:
            continue
        score = equivalence_score(original, candidate, registry)
        scored.append((candidate, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


# ── Scoring Components ───────────────────────────────────────────

def _capability_score(original: ModelInfo, candidate: ModelInfo) -> float:
    """Score based on capability overlap."""
    orig_caps = set(original.capabilities)
    cand_caps = set(candidate.capabilities)

    if not orig_caps:
        return 0.5  # Unknown capabilities

    overlap = len(orig_caps & cand_caps)
    return overlap / len(orig_caps)


def _tier_score(original: ModelInfo, candidate: ModelInfo) -> float:
    """Score based on tier compatibility."""
    if original.tier == candidate.tier:
        return 1.0

    # Define tier distances
    tier_order = {
        "flagship": 4,
        "reasoning": 4,
        "balanced": 3,
        "reasoning_fast": 2,
        "fast": 1,
    }

    orig_level = tier_order.get(original.tier, 2)
    cand_level = tier_order.get(candidate.tier, 2)
    distance = abs(orig_level - cand_level)

    # Penalty for each tier distance
    if distance == 0:
        return 1.0
    elif distance == 1:
        return 0.7
    elif distance == 2:
        return 0.4
    else:
        return 0.2


def _context_score(original: ModelInfo, candidate: ModelInfo) -> float:
    """Score based on context window compatibility."""
    if candidate.context_window >= original.context_window:
        return 1.0  # Candidate can handle everything the original can

    # Partial credit if context window is at least 50% of original
    ratio = candidate.context_window / original.context_window
    return max(0.0, ratio)

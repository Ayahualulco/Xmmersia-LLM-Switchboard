"""
Basic Health Check Example
══════════════════════════

The simplest possible usage — check if a model is healthy before calling it.
"""

from llm_switchboard import Switchboard

sb = Switchboard()

# Check a specific model
health = sb.check("claude-opus-4-6")

print(f"Model:          {health['model']}")
print(f"Provider:       {health['provider']}")
print(f"Status:         {health['status']}")
print(f"Confidence:     {health['confidence']:.0%}")
print(f"Recommendation: {health['recommendation']}")

# Act on the recommendation
if health["recommendation"] == "proceed":
    print("\n✓ Safe to call Claude Opus 4.6")
elif health["recommendation"] == "caution":
    print("\n⚠ Claude Opus 4.6 may be degraded — proceed with caution")
elif health["recommendation"] == "reroute":
    print("\n✗ Claude Opus 4.6 is having issues")
    if health["alternatives"]:
        best = health["alternatives"][0]
        print(f"  → Suggested alternative: {best['model']} (match: {best['match_score']:.0%})")

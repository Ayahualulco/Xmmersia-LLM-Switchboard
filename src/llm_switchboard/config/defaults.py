"""
Default configuration for LLM-Switchboard.
═══════════════════════════════════════════

Sensible defaults that work out of the box.
Override via environment variables, config file, or constructor args.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────

CONFIG_DIR = Path(__file__).parent
PROVIDERS_YAML = CONFIG_DIR / "providers.yaml"

# ── Health Engine Defaults ───────────────────────────────────────

DEFAULT_POLLING_INTERVAL = 60       # seconds between status page polls
DEFAULT_CACHE_TTL = 30              # seconds before a cached health check expires
DEFAULT_REQUEST_TIMEOUT = 10        # seconds for HTTP requests to status pages

# ── Health Scoring Weights ───────────────────────────────────────
# How much each signal source contributes to the overall health score.
# Must sum to 1.0.

STATUS_PAGE_WEIGHT = 0.6           # Provider's own status page
PROBE_WEIGHT = 0.3                 # Active probing results (if enabled)
COMMUNITY_WEIGHT = 0.1             # Community signals (future)

# ── Health Thresholds ────────────────────────────────────────────
# Score boundaries for health status classification.
# Score is 0.0 (dead) to 1.0 (perfectly healthy).

HEALTHY_THRESHOLD = 0.7            # >= this → healthy
DEGRADED_THRESHOLD = 0.3           # >= this and < healthy → degraded
# < DEGRADED_THRESHOLD → down

# ── Confidence Thresholds ────────────────────────────────────────

HIGH_CONFIDENCE = 0.85             # Very sure about the health assessment
MEDIUM_CONFIDENCE = 0.6            # Moderate certainty
LOW_CONFIDENCE = 0.4               # Significant uncertainty

# ── Probing Defaults ────────────────────────────────────────────

PROBE_ENABLED = False              # Active probing disabled by default (costs tokens)
PROBE_INTERVAL = 300               # seconds between probe checks (if enabled)
PROBE_PROMPT = "Say 'ok' and nothing else."
PROBE_MAX_TOKENS = 5
PROBE_TIMEOUT = 15                 # seconds

# ── Provenance Defaults ─────────────────────────────────────────

STAMP_STORAGE_ENABLED = True       # Store stamps for audit trail
STAMP_STORAGE_BACKEND = "memory"   # "memory" | "sqlite" | "file"
STAMP_RETENTION_DAYS = 90          # How long to keep stamps

# ── API Server Defaults ─────────────────────────────────────────

API_HOST = "0.0.0.0"
API_PORT = 8080

# ── Recommendation Mapping ───────────────────────────────────────
# Maps health status to default recommendation (overridden by policy).

DEFAULT_RECOMMENDATIONS = {
    "healthy": "proceed",
    "degraded": "caution",
    "down": "reroute",
    "unknown": "caution",
}

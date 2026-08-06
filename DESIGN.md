# LLM-Switchboard — Design Document

> This is the internal design document. For usage, see README.md.
> For the full design rationale, architecture details, and roadmap,
> this document is the authoritative reference.

---

## 1. Problem Statement

Every AI application that calls LLM providers faces a fragile reality: providers go down, degrade silently, or return lower-quality output without any visible error. Existing LLM gateways (Bifrost, LiteLLM, Portkey) handle failover reactively — your request fails, *then* they retry. This is fine for chatbots. It is not fine for grading student exams, generating legal documents, or producing medical summaries.

Switchboard exists to answer a different question: **"What is the state of the world right now, and what should I do about it — before I make the call?"**

### Design Goals

1. **Proactive, not reactive** — Check health *before* calling, not after failing.
2. **Advisory, not invasive** — Don't sit in the request path. Don't proxy traffic. Zero latency overhead.
3. **Policy-aware** — What you do about a degraded model depends on what's at stake. A chatbot reroutes silently. A graded exam stops and alerts a human.
4. **Provenance-first** — Every routing decision produces an auditable stamp. Months later, you can explain why an output was generated the way it was.
5. **Framework-agnostic** — Works with any LLM client, any framework, any language (via REST API).

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    Switchboard                       │
│                                                      │
│   check(model)  →  HealthEngine  →  HealthAssessment │
│   route(model, policy)  →  Router  →  RoutingResult  │
│   stamp(...)  →  Stamper  →  ProvenanceStamp          │
│                                                      │
│   ┌──────────┐  ┌────────┐  ┌─────────┐             │
│   │ Providers│  │ Models │  │ Policies│             │
│   │ Registry │  │Registry│  │ Engine  │             │
│   └──────────┘  └────────┘  └─────────┘             │
└─────────────────────────────────────────────────────┘
         │                          │
    ┌────▼─────┐              ┌─────▼─────┐
    │ Status   │              │ Active    │
    │ Pages    │              │ Probes    │
    │(external)│              │(optional) │
    └──────────┘              └───────────┘
```

### Component Responsibilities

| Component | Responsibility |
|-----------|---------------|
| **Switchboard** | Public API facade. Three methods: `check()`, `route()`, `stamp()`. |
| **HealthEngine** | Aggregates signals, computes weighted health scores, classifies status. |
| **Router** | Takes health assessment + policy → decides proceed/reroute/warn/stop. |
| **Stamper** | Generates provenance stamps with confidence flags. Maintains audit trail. |
| **HealthCache** | Thread-safe TTL cache. Prevents hammering status pages on every call. |
| **ModelRegistry** | Catalog of all known models with capabilities, tiers, context windows. |
| **Equivalence** | Capability-aware model substitution scoring. |
| **Providers** | Adapters for each LLM provider (status page + optional probe). |
| **Policies** | FAST / CAREFUL / CRITICAL presets. Custom policy support. |

### Key Design Decisions

- **No proxy pattern.** Switchboard never touches your LLM traffic. It's a sidecar intelligence layer.
- **Weighted multi-signal scoring.** A single status page is not enough — probes and community signals add nuance. Weights re-normalize automatically when fewer signals are available.
- **Policy as data.** Policies are plain dicts, not code. This makes them serializable, storable, and transferable across languages.
- **Stamps are self-contained.** Every stamp includes the full context needed to reconstruct the decision later. No external references required.

---

## 3. Health Scoring

The health engine aggregates up to three signal sources into a single health score per model.

### Signal Sources

| Source | Weight | Description |
|--------|--------|-------------|
| **Status page** | 0.6 | Provider's public status page (Atlassian Statuspage JSON, etc.) |
| **Active probe** | 0.3 | Lightweight API call to verify the model responds (costs tokens, disabled by default) |
| **Community** | 0.1 | Community signals — DownDetector, social media (future, placeholder) |

### Scoring Algorithm

```
score = Σ(signal_score × weight) / Σ(available_weights)
```

When only 1-2 signals are available, the weights re-normalize automatically. For example, with only a status page signal:

```
score = (status_score × 0.6) / 0.6 = status_score
```

With status page + probe:

```
score = (status_score × 0.6 + probe_score × 0.3) / 0.9
```

### Classification

| Score Range | Status | Default Recommendation |
|-------------|--------|----------------------|
| ≥ 0.7 | Healthy | Proceed |
| ≥ 0.3 and < 0.7 | Degraded | Caution |
| < 0.3 | Down | Reroute |

### Confidence

Confidence reflects how much data we have, not how healthy the model is:

| Signals Available | Confidence |
|-------------------|------------|
| 3 | High (0.85) |
| 2 | Medium (0.60) |
| 1 | Low (0.40) |
| 0 | Unknown |

---

## 4. Routing Policies

Policies define what to do when a model is degraded or down. The key insight: **the right action depends on what's at stake**, not just the health status.

### Built-in Policies

| Policy | On Degraded | On Down | Use Case |
|--------|-------------|---------|----------|
| **FAST** | Reroute silently | Reroute silently | Chatbots, summaries, low-stakes generation |
| **CAREFUL** | Warn, proceed | Reroute with warning | Content generation, lesson plans, reports |
| **CRITICAL** | Stop, alert human | Stop, alert human | Grading, legal, medical, financial |

### Policy Structure

```python
{
    "criticality": "high",          # low | medium | high | critical
    "on_degraded": "warn",          # proceed | warn | reroute | stop
    "on_down": "reroute",           # reroute | stop | queue
    "acceptable_models": [...],     # Restrict alternatives to this list
    "priority": "quality",          # quality | speed | cost
    "min_status": "degraded",       # Minimum acceptable health status
    "max_latency_ms": 5000,         # Maximum acceptable latency
}
```

### Decision Flow

```
0. Trust gate (see §5) → refuse outright, or fall through
1. Assess model health → HealthAssessment
2. Classify status (healthy / degraded / down)
3. Look up policy action for that status
4. If rerouting: find best alternative via equivalence scoring
                 (candidates filtered by the same trust gate)
5. If all alternatives exhausted: stop
6. Return RoutingResult with action + reason
```

---

## 5. Trust Tier Gate

The health matrix answers "is this model *up*?" It cannot answer "is this model *proven*?" Those are different questions, and for graded work the second one matters more. A model can report perfectly operational and still be the wrong thing to hand a student's exam to.

So Switchboard runs a trust gate **before** the operational health matrix. **Honesty before uptime.** A model refused on trust is never health-checked at all — it is excluded on what it is, not on how it happens to be behaving right now.

### Gate Table (L'Atelier llm-switchboard §06)

| Trust tier | FAST (learner-facing) | FAST (internal) | CAREFUL | CRITICAL |
|-----------|----------------------|-----------------|---------|----------|
| **trusted** | Allowed | Allowed | Allowed | Allowed |
| **watched** | Allowed | Allowed | Allowed | **Refused** |
| **untrusted** | **Refused** | Allowed | **Refused** | **Refused** |

A refused model reroutes to a trust-eligible alternative, or stops if none exists. `_find_alternative` applies the same gate to every candidate, so a health-triggered reroute cannot land on a model the policy would have refused directly.

Only `criticality: "critical"` triggers the CRITICAL-tier refusal. `criticality: "high"` maps to no built-in preset, and widening the gate to cover it silently would surprise custom-policy authors.

An unrecognized `trust_tier` value is treated as `untrusted` and logged. The refusal reason records the tier as actually configured, not the normalized value — provenance should show the real bad data.

### Scope in This Repository

Tiers here are **static**: assigned by hand in `providers.yaml`, read by the Router. The L'Atelier `llm-switchboard` document derives them from a weighted trust score (hallucination benchmarks, fabrication tests, production telemetry) on a refresh cadence. That derivation is deliberately deferred; none of its machinery exists in this codebase.

**The L'Atelier `llm-switchboard` document, §05 (Trust Tier) and §06 (Trust Tier Gate), is the source of truth.** This section summarizes it and defers to it on every point of conflict.

---

## 6. Model Equivalence

When rerouting, Switchboard needs to pick the best alternative. Naive approaches (random, round-robin) ignore that models differ in capabilities, quality tiers, and context windows.

### Scoring Formula

```
equivalence_score = (capability_overlap × 0.50) + (tier_compatibility × 0.30) + (context_ratio × 0.20)
```

### Components

| Factor | Weight | How It's Computed |
|--------|--------|-------------------|
| **Capability overlap** | 50% | Jaccard similarity of capability sets (intersection / union) |
| **Tier compatibility** | 30% | Distance penalty: same tier = 1.0, ±1 tier = 0.7, ±2 = 0.4, ±3+ = 0.2 |
| **Context window** | 20% | min(candidate / source, 1.0) — penalizes smaller windows, doesn't reward larger |

### Tier Hierarchy

```
flagship > balanced > fast
reasoning > reasoning_fast
```

This ensures that a flagship model reroutes to another flagship (score 1.0) before falling back to a balanced model (score ~0.8).

---

## 7. Provenance Stamps

Every routing decision produces a self-contained provenance stamp.

### Stamp Format

```json
{
    "stamp_id": "stamp_abc123def456",
    "switchboard_version": "1.0.0",
    "timestamp": "2026-03-07T14:30:00Z",
    "requested_model": "claude-opus-4-6",
    "actual_model": "gpt-4o",
    "provider_status_at_call": {
        "anthropic": "minor_outage",
        "openai": "operational"
    },
    "action": "rerouted",
    "reason": "Primary model degraded; rerouted to gpt-4o (match score: 0.87)",
    "confidence_flag": "review_recommended",
    "health_snapshot_id": "snap_789abc",
    "trust_tier_at_call": "trusted",
    "metadata": {}
}
```

### Confidence Flags

| Condition | Flag | Meaning |
|-----------|------|---------|
| Primary model used, healthy | `nominal` | Output generated under normal conditions |
| Rerouted to alternative | `review_recommended` | Output from a substitute model — may differ in style/quality |
| Warned or stopped | `low_confidence` | Something was wrong; output may be unreliable or absent |

### Why Provenance Matters

In education (Xmmersia's domain), provenance is not optional:

- **FERPA compliance** — If a graded exam was generated during a provider outage, that's auditable.
- **Quality assurance** — Reviewing outputs flagged `review_recommended` catches model-switch artifacts.
- **Incident response** — When a batch of outputs looks off, stamps pinpoint which were affected by provider issues.

---

## 8. Provider Adapters

Each provider implements a simple adapter interface:

```python
class BaseProvider:
    async def fetch_status(self) -> dict        # Required: check status page
    async def probe(self, model: str) -> dict   # Optional: active health probe
    def list_models(self) -> list[str]           # Required: known model IDs
```

### Implementation Status

| Provider | Status Page | Active Probe | Notes |
|----------|------------|-------------|-------|
| **Anthropic** | Atlassian Statuspage | `/v1/messages` | Full implementation |
| **OpenAI** | Atlassian Statuspage | `/v1/chat/completions` | Full implementation |
| **Google** | Custom format (fallback) | `/v1beta/models/{m}:generateContent` | Full implementation |
| **xAI** | Custom format (reachability) | `/v1/chat/completions` (OpenAI-compat) | Full implementation |
| **Mistral** | Atlassian Statuspage | — | Status page only |
| **Cohere** | Atlassian Statuspage | — | Status page only |
| **Groq** | Atlassian Statuspage | — | Status page only |
| **Together** | Atlassian Statuspage | — | Status page only |
| **Bedrock** | — | — | Placeholder (needs boto3) |

### Adding a Provider

1. Subclass `BaseProvider` in `providers/`
2. Implement `fetch_status()` and optionally `probe()`
3. Add to `PROVIDER_REGISTRY` in `providers/__init__.py`
4. Add models to `config/providers.yaml`

See [docs/providers.md](docs/providers.md) for the full guide.

---

## 9. Caching

The `HealthCache` is a thread-safe, TTL-based in-memory cache that prevents hammering status pages.

- **Default TTL:** 30 seconds
- **Thread safety:** All public methods acquire a `threading.Lock`
- **Automatic cleanup:** Expired entries are removed on access and via explicit `cleanup()`
- **Stats:** Hit/miss/expiry counters for observability

### Why Not Redis?

For v1.0, in-memory is the right choice:
- Zero external dependencies
- Sub-microsecond reads
- Health checks are ephemeral by nature — 30-second TTL means stale cache is bounded

Redis/Memcached support is planned for multi-instance deployments in a future version.

---

## 10. Interfaces

### Python API

```python
from llm_switchboard import Switchboard

sb = Switchboard()
health = sb.check("claude-opus-4-6")
result = sb.route("claude-opus-4-6", policy="careful")
stamp  = sb.stamp(model_requested=..., model_used=..., action_taken=..., reason=...)
```

### REST API (FastAPI)

```
GET  /health/{model}           — Check one model
GET  /health                   — Check all models
POST /route                    — Route with policy
GET  /providers                — List providers
GET  /providers/{p}/models     — List provider's models
GET  /stamp/{id}               — Retrieve a stamp
GET  /status                   — Switchboard status
```

### CLI (Click)

```
switchboard check <model>      — Health check
switchboard status             — All providers summary
switchboard route -m <model> -p <policy>  — Route
switchboard providers          — List providers and models
switchboard serve              — Start REST API
switchboard config             — Configuration (v1.1)
```

---

## 11. Xmmersia Context

Switchboard was built for the **Rozafa Hub** — Xmmersia's infrastructure layer for AI-powered education. In this context:

- **Teaching agents** use CAREFUL policy — a rerouted lesson plan is better than no lesson plan, but we want to know about it.
- **Grading agents** use CRITICAL policy — a grade generated by a degraded model must be flagged for human review. No silent rerouting.
- **The Model Health Sentinel** runs Switchboard as a service, providing real-time health intelligence to all agents in the hub.

But Switchboard itself is general-purpose. It has no Xmmersia-specific code, no education-specific logic. Any team running AI agents in production can use it.

---

## 12. Future Work

| Feature | Version | Description |
|---------|---------|-------------|
| Community signals | v1.1 | DownDetector integration, social media sentiment |
| Persistent stamp storage | v1.1 | SQLite and file-based backends |
| Configuration CLI | v1.1 | `switchboard config` for runtime configuration |
| Webhook notifications | v1.2 | Alert on status changes (Slack, email, custom) |
| Cost-aware routing | v1.2 | Factor token pricing into routing decisions |
| Multi-instance cache | v1.3 | Redis/Memcached backend for distributed deployments |
| Provider SDK probes | v1.3 | Use official SDKs instead of raw HTTP for probing |
| Bedrock integration | v1.3 | Full AWS Bedrock adapter with boto3 |

---

## 13. Non-Goals

Things Switchboard intentionally does not do:

- **Proxy LLM traffic** — We're advisory. Use your own client.
- **Manage API keys** — Keys are sourced from environment variables. We never store them.
- **Rate limiting** — That's your gateway's job.
- **Response caching** — We cache *health checks*, not LLM responses.
- **Model fine-tuning** — Out of scope entirely.

---

*Switchboard watches so agents can work. It routes so services never stop. And it stamps so the truth is always recoverable.*

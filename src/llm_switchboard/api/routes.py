"""
API Route Definitions
═════════════════════

REST endpoints for LLM-Switchboard.

    GET  /health/{model}              → health check for a specific model
    GET  /health                      → health of all tracked providers
    POST /route                       → route a request with policy
    GET  /providers                   → list all supported providers
    GET  /providers/{provider}/models → list models for a provider
    GET  /stamp/{stamp_id}            → retrieve a stored provenance stamp
    GET  /status                      → Switchboard's own health
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from llm_switchboard import Switchboard


# ── Request/Response Models ──────────────────────────────────────

class RouteRequest(BaseModel):
    preferred_model: str = "claude-opus-4-6"
    policy: str | dict = "careful"
    task_description: str | None = None


class RouteResponse(BaseModel):
    routed_to: str
    reason: str
    action: str
    provenance: dict


# ── App Factory ──────────────────────────────────────────────────

def create_app(switchboard: Switchboard | None = None) -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(
        title="LLM-Switchboard",
        description="Proactive LLM health intelligence, routing, and provenance stamping.",
        version="1.0.0",
    )

    # Initialize Switchboard (lazy — created on first request if not provided)
    state = {"sb": switchboard}

    def get_sb() -> Switchboard:
        if state["sb"] is None:
            state["sb"] = Switchboard()
        return state["sb"]

    # ── Health Endpoints ─────────────────────────────────────────

    @app.get("/health/{model}")
    async def check_model(model: str):
        """Health check for a specific model."""
        return get_sb().check(model)

    @app.get("/health")
    async def check_all():
        """Health of all tracked providers."""
        sb = get_sb()
        all_models = sb.list_models()
        results = {}
        for model_info in all_models:
            model_id = model_info["id"]
            results[model_id] = sb.check(model_id)
        return results

    # ── Routing Endpoint ─────────────────────────────────────────

    @app.post("/route")
    async def route_request(req: RouteRequest):
        """Route a request with a policy."""
        result = get_sb().route(
            preferred_model=req.preferred_model,
            policy=req.policy,
            prompt=req.task_description,
        )
        return result.to_dict()

    # ── Provider Endpoints ───────────────────────────────────────

    @app.get("/providers")
    async def list_providers():
        """List all supported providers."""
        return {"providers": get_sb().list_providers()}

    @app.get("/providers/{provider}/models")
    async def list_provider_models(provider: str):
        """List models for a specific provider."""
        models = get_sb().list_models(provider=provider)
        if not models:
            raise HTTPException(status_code=404, detail=f"Provider '{provider}' not found")
        return {"provider": provider, "models": models}

    # ── Provenance Endpoints ─────────────────────────────────────

    @app.get("/stamp/{stamp_id}")
    async def get_stamp(stamp_id: str):
        """Retrieve a stored provenance stamp."""
        stamp = get_sb().get_stamp(stamp_id)
        if stamp is None:
            raise HTTPException(status_code=404, detail=f"Stamp '{stamp_id}' not found")
        return stamp

    # ── Status Endpoint ──────────────────────────────────────────

    @app.get("/status")
    async def switchboard_status():
        """Switchboard's own health and status."""
        return get_sb().status()

    return app

"""
LLM-Switchboard REST API
═════════════════════════

Run Switchboard as a service for non-Python applications.

    switchboard serve --port 8080

Provides health checks, routing, and provenance stamp retrieval
via a clean REST interface.
"""

from __future__ import annotations

from llm_switchboard.api.routes import create_app


def serve(host: str = "0.0.0.0", port: int = 8080) -> None:
    """Start the Switchboard API server."""
    import uvicorn

    app = create_app()
    uvicorn.run(app, host=host, port=port)


__all__ = ["create_app", "serve"]

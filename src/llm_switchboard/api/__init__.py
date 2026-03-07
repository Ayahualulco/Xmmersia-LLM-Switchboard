"""
LLM-Switchboard REST API
"""

from llm_switchboard.api.routes import create_app
from llm_switchboard.api.server import serve

__all__ = ["create_app", "serve"]

"""Base agent abstraction and shared prompt."""

from app.agents.base.agent import BaseAgent
from app.agents.base.prompt import BASE_SYSTEM_PROMPT

__all__ = ["BASE_SYSTEM_PROMPT", "BaseAgent"]

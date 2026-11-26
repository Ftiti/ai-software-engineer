"""Application settings loaded from environment variables and an optional ``.env`` file."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["ollama", "openai", "gemini", "groq"]
Temperature = Annotated[float, Field(ge=0.0, le=2.0)]


class Settings(BaseSettings):
    """Typed runtime configuration. Every field maps to an upper-case environment variable."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Active LLM provider and defaults shared by every provider
    llm_provider: LLMProviderName = "ollama"
    llm_temperature: Temperature = 0.0
    llm_timeout: float | None = Field(default=None, gt=0)  # seconds; None = no limit

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_temperature: Temperature | None = None  # None = use LLM_TEMPERATURE

    # OpenAI
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_temperature: Temperature | None = None

    # Google Gemini
    google_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_temperature: Temperature | None = None

    # Groq
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.1-8b-instant"
    groq_temperature: Temperature | None = None

    # Tools
    tool_timeout: float | None = Field(default=60.0, gt=0)  # seconds per tool call; None = no limit

    # MCP
    mcp_config_path: Path = Path("mcp_servers.json")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()

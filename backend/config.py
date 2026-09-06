import os
from typing import List

class Settings:
    # Environment mode
    ENABLE_DEV_TRACE: bool = os.getenv("ENABLE_DEV_TRACE", "false").lower() == "true"

    # API configuration
    ALLOWED_ORIGINS: List[str] = [origin.strip() for origin in os.getenv("ALLOWED_ORIGINS", "*").split(",")]
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # Session configuration
    SESSION_TTL_SECONDS: int = int(os.getenv("SESSION_TTL_SECONDS", "86400")) # Default 24 hours

    # Model configuration
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "intfloat/multilingual-e5-large")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "groq")
    LLM_FALLBACK_MODEL: str = os.getenv("LLM_FALLBACK_MODEL", "llama-3.1-8b-instant")

settings = Settings()

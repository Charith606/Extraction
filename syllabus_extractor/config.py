"""
Centralized Configuration for Syllabus Extractor & Verification Studio.
Allows swapping models, providers, and escalation settings via environment variables or .env file.
"""

import os
from typing import Optional
from pydantic import BaseModel, Field

# Load .env file if python-dotenv is available or manually parse
def _load_env_file():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass

_load_env_file()


class Settings(BaseModel):
    # Primary & Secondary Providers: 'gemini', 'groq', 'openai', 'anthropic', 'deepseek', 'ollama', 'heuristic'
    primary_provider: str = Field(default_factory=lambda: os.getenv("LLM_PRIMARY_PROVIDER", "").lower() or "auto")
    backup_provider: str = Field(default_factory=lambda: os.getenv("LLM_BACKUP_PROVIDER", "").lower() or "heuristic")
    
    # Modernized Model Names
    gemini_model: str = Field(default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-1.5-flash"))
    groq_model: str = Field(default_factory=lambda: os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b"))
    ollama_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "qwen2.5:7b"))
    openai_model: str = Field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    claude_primary_model: str = Field(default_factory=lambda: os.getenv("CLAUDE_PRIMARY_MODEL", "claude-3-5-haiku-latest"))
    claude_escalation_model: str = Field(default_factory=lambda: os.getenv("CLAUDE_ESCALATION_MODEL", "claude-3-5-sonnet-latest"))
    deepseek_model: str = Field(default_factory=lambda: os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))

    # Escalation & Validation Settings
    enable_escalation: bool = Field(default_factory=lambda: os.getenv("ENABLE_ESCALATION", "true").lower() == "true")
    max_line_drift_tolerance: int = 2
    ollama_host: str = Field(default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434"))


# Global singleton instance
config = Settings()

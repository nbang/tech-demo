"""Configuration, sourced from environment (LLM_* / TEXT2SPARQL_*) with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Settings:
    # LLM used for SPARQL generation, via the OpenAI SDK. Any OpenAI-compatible endpoint works,
    # including Ollama (which serves one at /v1), vLLM, and hosted OpenAI/NVIDIA endpoints.
    #   LLM_BASE_URL — the OpenAI-compatible endpoint (include /v1)
    #   LLM_MODEL    — the model name served there
    #   LLM_API_KEY  — bearer token; only needed for hosted endpoints (Ollama ignores it)
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gemma4:31b")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    request_timeout: float = float(os.getenv("TEXT2SPARQL_TIMEOUT", "180"))

    # Self-repair: total generation attempts. If a query raises a SPARQL error, the error is fed
    # back to the model to fix (a valid query that returns 0 rows is left alone). 1 disables repair.
    max_attempts: int = int(os.getenv("TEXT2SPARQL_MAX_ATTEMPTS", "2"))

    # Storage
    data_dir: Path = Path(os.getenv("TEXT2SPARQL_DATA_DIR", ".text2sparql"))

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

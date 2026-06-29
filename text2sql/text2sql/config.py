"""Configuration, sourced from environment (TEXT2SQL_* / OLLAMA_*) with sensible defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # Ollama (OpenAI-compatible native API)
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    gen_model: str = os.getenv("TEXT2SQL_GEN_MODEL", "qwen3.5:4b")
    embed_model: str = os.getenv("TEXT2SQL_EMBED_MODEL", "nomic-embed-text")
    request_timeout: float = float(os.getenv("TEXT2SQL_TIMEOUT", "180"))

    # RAG
    top_k: int = int(os.getenv("TEXT2SQL_TOP_K", "8"))

    # Storage
    data_dir: Path = Path(os.getenv("TEXT2SQL_DATA_DIR", ".text2sql"))

    # Execution safety. The default is full execution (per project choice); set
    # TEXT2SQL_READONLY=1 to force every query into a READ ONLY transaction.
    read_only: bool = _bool("TEXT2SQL_READONLY", False)
    max_rows: int = int(os.getenv("TEXT2SQL_MAX_ROWS", "500"))

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

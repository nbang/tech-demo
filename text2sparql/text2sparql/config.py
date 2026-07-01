"""Configuration, sourced from environment (TEXT2SPARQL_* / OLLAMA_*) with sensible defaults."""

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
    # Ollama — the local LLM used for SPARQL generation.
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    gen_model: str = os.getenv("TEXT2SPARQL_GEN_MODEL", "gemma4:31b")
    request_timeout: float = float(os.getenv("TEXT2SPARQL_TIMEOUT", "180"))

    # Hybrid reasoning models (qwen3.5, …) emit a slow chain-of-thought. For this structured task it
    # adds latency without helping, so we disable it by default. Set TEXT2SPARQL_THINK=1 to re-enable.
    think: bool = _bool("TEXT2SPARQL_THINK", False)

    # Self-repair: total generation attempts. If a query raises a SPARQL error, the error is fed
    # back to the model to fix (a valid query that returns 0 rows is left alone). 1 disables repair.
    max_attempts: int = int(os.getenv("TEXT2SPARQL_MAX_ATTEMPTS", "2"))

    # Introspection limits (keep ingest cheap on large graphs).
    max_classes: int = int(os.getenv("TEXT2SPARQL_MAX_CLASSES", "200"))
    sample_limit: int = int(os.getenv("TEXT2SPARQL_SAMPLE_LIMIT", "2000"))

    # Storage
    data_dir: Path = Path(os.getenv("TEXT2SPARQL_DATA_DIR", ".text2sparql"))

    # Execution safety. Unlike SQL, most SPARQL endpoints are query-only; the default
    # therefore REJECTS SPARQL Update (INSERT/DELETE/LOAD/...). Set TEXT2SPARQL_ALLOW_UPDATE=1
    # to permit mutating queries against a writable store.
    allow_update: bool = _bool("TEXT2SPARQL_ALLOW_UPDATE", False)
    max_rows: int = int(os.getenv("TEXT2SPARQL_MAX_ROWS", "500"))

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()

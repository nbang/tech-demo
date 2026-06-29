"""Thin client over a self-hosted Ollama instance for generation and embeddings."""

from __future__ import annotations

import json
import re

import httpx

from .config import settings

_SQL_START = re.compile(r"\b(WITH|SELECT|INSERT|UPDATE|DELETE)\b", re.IGNORECASE)
_FENCE = re.compile(r"```(?:sql|json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)


class LLMError(RuntimeError):
    pass


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.ollama_base_url, timeout=settings.request_timeout)


def embed(text: str) -> list[float]:
    """Return an embedding vector for `text` using the configured embedding model."""
    try:
        with _client() as c:
            resp = c.post(
                "/api/embeddings",
                json={"model": settings.embed_model, "prompt": text},
            )
            resp.raise_for_status()
            return resp.json()["embedding"]
    except httpx.HTTPError as e:
        raise LLMError(f"Embedding request failed ({settings.embed_model}): {e}") from e


def generate_sql(system_prompt: str, user_prompt: str) -> dict:
    """Ask the model for SQL. Returns {'sql', 'explanation', 'tables_used'}.

    The model is asked to reply with a JSON object; we parse it leniently and fall back
    to extracting the raw SQL, so the tool works across instruct models.
    """
    try:
        with _client() as c:
            resp = c.post(
                "/api/chat",
                json={
                    "model": settings.gen_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "stream": False,
                    "think": False,  # skip reasoning traces on models that support it
                    "options": {"temperature": 0},
                },
            )
            resp.raise_for_status()
            content = resp.json()["message"]["content"]
    except httpx.HTTPError as e:
        raise LLMError(f"Generation request failed ({settings.gen_model}): {e}") from e

    return _parse(content)


def _parse(content: str) -> dict:
    content = _THINK.sub("", content).strip()
    # Preferred: a JSON object, possibly wrapped in a ```json fence.
    for candidate in (content, _strip_fence(content)):
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "sql" in data:
            return {
                "sql": (data.get("sql") or "").strip(),
                "explanation": data.get("explanation", ""),
                "tables_used": data.get("tables_used", []),
            }
    # Fallback: the response is the SQL itself.
    return {"sql": _extract_sql(content), "explanation": "", "tables_used": []}


def _strip_fence(text: str) -> str | None:
    m = _FENCE.search(text)
    return m.group(1).strip() if m else None


def _extract_sql(text: str) -> str:
    fenced = _strip_fence(text)
    if fenced is not None:
        text = fenced
    m = _SQL_START.search(text)
    if m:
        text = text[m.start() :]
    semi = text.find(";")
    if semi != -1:
        text = text[: semi + 1]
    return text.strip()

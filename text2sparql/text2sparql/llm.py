"""Thin client for SPARQL generation via a local Ollama model."""

from __future__ import annotations

import json
import re

import httpx

from .config import settings

_SPARQL_START = re.compile(r"\b(PREFIX|BASE|SELECT|ASK|CONSTRUCT|DESCRIBE)\b", re.IGNORECASE)
# Match a fenced block with any language tag (```json, ```sparql, ``` …), capturing its body.
_FENCE = re.compile(r"```[ \t]*\w*[ \t]*\n?(.*?)```", re.DOTALL)
# Some models (e.g. qwen3.5) emit a <think>…</think> chain-of-thought before the answer.
# Strip it so it can't leak into the parsed JSON / SPARQL.
_THINK = re.compile(r"<think>.*?</think>", re.IGNORECASE | re.DOTALL)
# SPARQL solution modifiers that legitimately follow the closing "}" of the WHERE block.
_MODIFIERS = re.compile(
    r"\s*((?:(?:ORDER\s+BY|GROUP\s+BY|HAVING|LIMIT|OFFSET|VALUES)[^\n]*\n?)*)",
    re.IGNORECASE,
)


class LLMError(RuntimeError):
    pass


def generate_sparql(system_prompt: str, user_prompt: str) -> dict:
    """Ask the local Ollama model for SPARQL. Returns {'sparql', 'explanation', 'classes_used'}.

    The model is asked to follow a JSON contract, but we stay lenient: if it returns raw
    SPARQL instead, we extract it.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        with httpx.Client(base_url=settings.ollama_base_url, timeout=settings.request_timeout) as c:
            resp = c.post(
                "/api/chat",
                json={
                    "model": settings.gen_model,
                    "messages": messages,
                    "stream": False,
                    "think": settings.think,
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
    # A reasoning model whose closing </think> got cut off leaves a dangling open block;
    # drop everything up to the last </think> if only the opener survived parsing above.
    if "</think>" in content:
        content = content.rsplit("</think>", 1)[-1].strip()
    # Chat models: a JSON object, possibly inside a ```json fence or wrapped in preamble prose.
    # The third candidate is the outermost {...} substring, which survives leading/trailing text.
    candidates = [content, _strip_fence(content)]
    i, j = content.find("{"), content.rfind("}")
    if i != -1 and j > i:
        candidates.append(content[i : j + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "sparql" in data:
            return {
                "sparql": (data.get("sparql") or "").strip(),
                "explanation": data.get("explanation", ""),
                "classes_used": data.get("classes_used", []),
            }
    # Fallback: the response is the SPARQL itself.
    return {"sparql": _extract_sparql(content), "explanation": "", "classes_used": []}


def _strip_fence(text: str) -> str | None:
    m = _FENCE.search(text)
    return m.group(1).strip() if m else None


def _extract_sparql(text: str) -> str:
    fenced = _strip_fence(text)
    if fenced is not None:
        text = fenced
    text = re.sub(r"^\s*(SPARQL|Query|Answer)\s*[:>]\s*", "", text, flags=re.IGNORECASE)
    m = _SPARQL_START.search(text)
    if m:
        text = text[m.start():]
    # Drop trailing prose after the query's final closing brace — but KEEP any solution
    # modifiers (ORDER BY / GROUP BY / HAVING / LIMIT / OFFSET / VALUES), which legitimately
    # follow the brace, before cutting whatever prose comes after them.
    last = text.rfind("}")
    if last != -1:
        tail = _MODIFIERS.match(text[last + 1:])
        text = text[: last + 1] + (("\n" + tail.group(1).strip()) if tail and tail.group(1).strip() else "")
    return text.strip()

"""Thin client for SPARQL generation via any OpenAI-compatible chat endpoint (incl. Ollama's /v1)."""

from __future__ import annotations

import json

from openai import OpenAI, OpenAIError

from .config import settings


class LLMError(RuntimeError):
    pass


def generate_sparql(system_prompt: str, user_prompt: str) -> dict:
    """Ask the configured LLM for SPARQL. Returns {'sparql', 'explanation', 'classes_used'}.

    We request a JSON object (response_format) and parse it. The SDK-level JSON mode plus the
    system prompt's contract mean we no longer need to salvage fenced or raw-SPARQL responses.
    """
    # Ollama's OpenAI-compatible endpoint ignores the api_key but the SDK requires a non-empty
    # one, so fall back to a placeholder.
    client = OpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key or "ollama",
        timeout=settings.request_timeout,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
    except OpenAIError as e:
        raise LLMError(f"Generation request failed ({settings.llm_model}): {e}") from e

    return _parse(content)


def _parse(content: str) -> dict:
    """Parse the model's JSON object into our result dict.

    With response_format=json_object the content is already a JSON object; we keep one small
    safeguard (grab the outermost {...}) in case a model wraps it in stray text.
    """
    data = None
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        i, j = content.find("{"), content.rfind("}")
        if i != -1 and j > i:
            try:
                data = json.loads(content[i : j + 1])
            except json.JSONDecodeError:
                data = None

    if not isinstance(data, dict):
        # Let the caller's self-repair loop treat an unparseable reply as "no SPARQL".
        return {"sparql": "", "explanation": "", "classes_used": []}
    return {
        "sparql": (data.get("sparql") or "").strip(),
        "explanation": data.get("explanation", ""),
        "classes_used": data.get("classes_used", []),
    }

from __future__ import annotations

import os
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "anthropic/claude-3.5-sonnet"
DEFAULT_TIMEOUT = 120.0


class OpenRouterError(RuntimeError):
    pass


def chat_completion(
    *,
    system_prompt: str,
    user_message: str,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    temperature: float = 0.0,
) -> str:
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise OpenRouterError("Не задан OPENROUTER_API_KEY (env или --api-key)")

    url = f"{(base_url or os.getenv('OPENROUTER_BASE_URL') or DEFAULT_BASE_URL).rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "https://github.com/local/dxf-converter"),
        "X-Title": os.getenv("OPENROUTER_APP_TITLE", "DXF Converter Eval"),
    }
    payload: dict[str, Any] = {
        "model": model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
    }

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        raise OpenRouterError(f"OpenRouter HTTP {response.status_code}: {response.text[:500]}")

    data = response.json()
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError(f"Неожиданный ответ OpenRouter: {data!r}") from exc

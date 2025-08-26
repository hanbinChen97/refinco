"""
Perplexity wrapper using official API via OpenAI-compatible client or REST.

Environment variables:
- PERPLEXITY_API_KEY (required)
- PERPLEXITY_API_BASE (optional; defaults to https://api.perplexity.ai)

Exports:
- perplexity_generate_text(prompt: str, model: str = "sonar-pro") -> dict
    Returns {"text": str, "sources": list[dict]} when available.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv
import requests

# Load .env from project root (you run Python from the root)
# A simple load_dotenv() is sufficient in this setup.
load_dotenv()


def _get_ppx_base_and_key() -> Tuple[str, str]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise EnvironmentError("PERPLEXITY_API_KEY is not set")
    base = os.getenv("PERPLEXITY_API_BASE", "https://api.perplexity.ai")
    return base, api_key


def _extract_ppx_text_and_sources(resp_json: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    text = ""
    sources: List[Dict[str, Any]] = []

    # Text content
    if isinstance(resp_json, dict):
        # OpenAI-compatible chat/completions style
        choices = resp_json.get("choices")
        if isinstance(choices, list) and choices:
            msg = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(msg, dict):
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                # Perplexity sometimes adds citations in message
                for key in ("citations", "sources", "references", "search_results", "web_results", "evidence"):
                    if key in msg and isinstance(msg[key], list):
                        for it in msg[key]:
                            if not isinstance(it, dict):
                                continue
                            title = it.get("title") or it.get("name") or it.get("url")
                            url = it.get("url") or it.get("link")
                            snippet = it.get("snippet") or it.get("description")
                            source = {
                                "title": title,
                                "url": url,
                                "snippet": snippet,
                                "engine": "perplexity",
                            }
                            if source not in sources:
                                sources.append(source)

        # Some endpoints place citations at the top-level
        for key in ("citations", "sources", "references", "search_results", "web_results", "evidence"):
            if key in resp_json and isinstance(resp_json[key], list):
                for it in resp_json[key]:
                    if not isinstance(it, dict):
                        continue
                    title = it.get("title") or it.get("name") or it.get("url")
                    url = it.get("url") or it.get("link")
                    snippet = it.get("snippet") or it.get("description")
                    source = {
                        "title": title,
                        "url": url,
                        "snippet": snippet,
                        "engine": "perplexity",
                    }
                    if source not in sources:
                        sources.append(source)

    return text or "", sources


def perplexity_generate_text(prompt: str, *, model: str = "sonar-pro", response_format: Dict[str, Any] | None = None) -> Dict[str, Any]:
    base, key = _get_ppx_base_and_key()
    url = base.rstrip("/") + "/chat/completions"

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        "web_search_options": {
            "search_context_size": "high"
        }
    }
    
    if response_format:
        payload["response_format"] = response_format

    try:
        res = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        res.raise_for_status()
    except Exception as e:
        return {"text": f"[perplexity request failed: {e}]", "sources": []}

    data = res.json()
    text, sources = _extract_ppx_text_and_sources(data)
    return {"text": text, "sources": sources}


__all__ = [
    "perplexity_generate_text",
]


def main() -> None:
    """Minimal connectivity test when running this file directly.

    - Reads PERPLEXITY_API_KEY from env/.env (already loaded above).
    - Uses PERPLEXITY_MODEL if provided, else defaults to "sonar-pro".
    - Sends a fixed prompt and prints a short preview and sources count.
    """
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        print("SKIP: PERPLEXITY_API_KEY not set; set it in your environment/.env to run.")
        return

    prompt = "Search the web and summarize recent quantum computing developments."
    model = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
    print(f"Model: {model}")
    result = perplexity_generate_text(prompt, model=model)
    text = (result or {}).get("text", "")
    sources = (result or {}).get("sources", [])
    print(f"TEXT_LEN={len(text)} SOURCES={len(sources)}")

    if text:
        preview = text[:600]
        print("TEXT_PREVIEW:\n" + preview + ("..." if len(text) > 600 else ""))
    if sources:
        for i, s in enumerate(sources[:3], 1):
            print(f"  {i}. {s.get('title') or ''}\n     {s.get('url')}")


if __name__ == "__main__":
    main()

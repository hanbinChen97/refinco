"""
OpenAI web-search wrapper using the Responses API (defensive parsing).

Environment variables:
- OPENAI_API_KEY (required)
- OPENAI_BASE_URL (optional; for proxies)

Exports:
- generate_text_with_web_search(prompt: str, model: str = "gpt-4o-mini", user_location: dict | None = None,
                                                                search_context_size: str | None = None, force_tool: bool = False) -> dict
        Returns {"text": str, "sources": list[dict]} where sources are best-effort extracted.
- openai_web_search(query: str, *, model: str = "gpt-4o-mini") -> list[dict]
        Convenience function that queries the web and returns sources only.

Notes:
- This uses the Responses API web search tool. The current default tool is
    "web_search_preview" (e.g., "web_search_preview_2025_03_11"). We default to
    that and fall back to the older "web_search" name if needed.
- Source extraction now prefers URL citations in message content annotations
    (annotation.type == "url_citation") per the latest API docs, with fallbacks
    to prior experimental fields if present.
- If web search tooling is not enabled for the account or model, this will
    return text with an empty sources array.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import os
from dotenv import load_dotenv

load_dotenv()


def _get_openai_client():
    try:
        # Official OpenAI SDK (>= 1.0)
        from openai import OpenAI  # type: ignore
    except Exception as e:  # pragma: no cover - import-time failure
        raise RuntimeError(
            "openai package is required. Please ensure 'openai' is installed."
        ) from e

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("OPENAI_API_KEY is not set")

    base_url = os.getenv("OPENAI_BASE_URL")
    if base_url:
        client = OpenAI(api_key=api_key, base_url=base_url)
    else:
        client = OpenAI(api_key=api_key)
    return client


def _extract_text_and_sources(resp: Any) -> Tuple[str, List[Dict[str, Any]]]:
    """Best-effort extraction of plain text and sources/citations from a
    Responses API result. The structure may vary across SDK versions.

    Priority is given to `message.content[*].annotations` with
    annotation.type == "url_citation" as per the latest docs, then we fall back
    to earlier experimental shapes like "citations", "sources",
    "web_search_results", "references" when present.
    """

    def _get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    text = ""
    sources: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    # Newer SDKs expose a convenience property
    if hasattr(resp, "output_text") and isinstance(resp.output_text, str):
        text = resp.output_text

    # Try to walk through output content parts (Responses API shape)
    try:
        outputs = getattr(resp, "output", None)
        if isinstance(outputs, list):
            for out in outputs:
                content = _get(out, "content")
                if isinstance(content, list):
                    for part in content:
                        p_type = _get(part, "type")
                        # Primary text capture
                        if p_type == "output_text":
                            if not text:
                                txt = _get(part, "text")
                                if isinstance(txt, str):
                                    text = txt
                            # Parse URL citations from annotations
                            annotations = _get(part, "annotations")
                            if isinstance(annotations, list):
                                for ann in annotations:
                                    a_type = _get(ann, "type")
                                    if a_type == "url_citation":
                                        url = _get(ann, "url")
                                        if not url or not isinstance(url, str):
                                            continue
                                        title = _get(ann, "title") or url
                                        source = {
                                            "title": title,
                                            "url": url,
                                            # Optional location info if present
                                            "start_index": _get(ann, "start_index"),
                                            "end_index": _get(ann, "end_index"),
                                            "engine": "openai-web-search",
                                        }
                                        if url not in seen_urls:
                                            sources.append(source)
                                            seen_urls.add(url)

                        # Fallbacks for earlier/experimental fields (if present at content part level)
                        for key in ("citations", "sources", "web_search_results", "references"):
                            vals = _get(part, key)
                            if isinstance(vals, list):
                                for it in vals:
                                    if not isinstance(it, (dict,)):
                                        continue
                                    url = it.get("url") or it.get("link")
                                    if not url:
                                        continue
                                    title = it.get("title") or it.get("name") or url
                                    snippet = it.get("snippet") or it.get("description")
                                    source = {
                                        "title": title,
                                        "url": url,
                                        "snippet": snippet,
                                        "engine": "openai-web-search",
                                    }
                                    if url not in seen_urls:
                                        sources.append(source)
                                        seen_urls.add(url)
    except Exception:
        # Defensive: parsing variations shouldn't crash the call path
        pass

    # Fallback: dig into choices style response (some SDKs mirror ChatCompletion shape)
    if not text or not sources:
        try:
            choices = getattr(resp, "choices", None)
            if isinstance(choices, list) and choices:
                msg = choices[0].get("message") if isinstance(choices[0], dict) else None
                if isinstance(msg, dict):
                    content = msg.get("content")
                    if isinstance(content, str) and not text:
                        text = content
                    # Sometimes includes citations/sources arrays
                    for key in ("citations", "sources"):
                        arr = msg.get(key)
                        if isinstance(arr, list):
                            for it in arr:
                                if not isinstance(it, dict):
                                    continue
                                url = it.get("url") or it.get("link")
                                if not url:
                                    continue
                                title = it.get("title") or it.get("name") or url
                                snippet = it.get("snippet") or it.get("description")
                                source = {
                                    "title": title,
                                    "url": url,
                                    "snippet": snippet,
                                    "engine": "openai-web-search",
                                }
                                if url not in seen_urls:
                                    sources.append(source)
                                    seen_urls.add(url)
        except Exception:
            pass

    return text or "", sources


def generate_text_with_web_search(
    prompt: str,
    *,
    model: str = "gpt-4o-mini",
    user_location: Optional[Dict[str, Any]] = None,
    search_context_size: Optional[str] = None,  # "low" | "medium" | "high"
    force_tool: bool = False,
) -> Dict[str, Any]:
    """Call OpenAI Responses API with web search enabled and return text & sources.

    Parameters:
    - prompt: user prompt or instructions
    - model: model to use
    - user_location: optional dict to pass to the tool (e.g., {"type": "approximate", "country": "GB", ...})
    - search_context_size: optional "low" | "medium" | "high" for supported models
    - force_tool: if True, sets tool_choice to {"type": "web_search_preview"} to encourage lower latency/consistency

    Returns a dict: {"text": str, "sources": list[dict]}.
    """
    client = _get_openai_client()

    # Prefer the documented default: web_search_preview
    tool: Dict[str, Any] = {"type": "web_search_preview"}
    if user_location:
        tool["user_location"] = user_location
    if search_context_size:
        tool["search_context_size"] = search_context_size

    kwargs: Dict[str, Any] = {
        "model": model,
        "input": prompt,
        "tools": [tool],  # type: ignore[arg-type]
    }
    if force_tool:
        kwargs["tool_choice"] = {"type": "web_search_preview"}

    try:
        resp = client.responses.create(**kwargs)
    except Exception:
        # Fallback to older tool name if environment still expects it
        try:
            tool_fallback: Dict[str, Any] = {"type": "web_search"}
            if user_location:
                tool_fallback["user_location"] = user_location
            if search_context_size:
                tool_fallback["search_context_size"] = search_context_size
            kwargs_fb = dict(kwargs)
            kwargs_fb["tools"] = [tool_fallback]
            if force_tool:
                kwargs_fb["tool_choice"] = {"type": "web_search"}
            resp = client.responses.create(**kwargs_fb)
        except Exception as e:
            # Return graceful failure structure
            return {"text": f"[openai web-search failed: {e}]", "sources": []}

    text, sources = _extract_text_and_sources(resp)
    return {"text": text, "sources": sources}


def openai_web_search(query: str, *, model: str = "gpt-4o-mini") -> List[Dict[str, Any]]:
    """Convenience: run a simple query and return structured sources only."""
    result = generate_text_with_web_search(
        f"Search the web and summarize: {query}", model=model
    )
    return result.get("sources", [])

__all__ = [
    "generate_text_with_web_search",
    "openai_web_search",
]

"""
take input: company name
output: (email, number)

google search: {company name} contact page -> pages

llm select most relevant page ->(title, url)

crawl4ai -> page content

llm extract email and phone number
"""

import asyncio
import json
from typing import Tuple, Optional, Dict, List, Any
from crawl4ai import AsyncWebCrawler
from utils.google_search_api import google_search
from typing import List, Dict

# New wrappers
try:
    from utils.openai_llm import openai_web_search
except Exception:
    openai_web_search = None  # type: ignore

try:
    from utils.perplexity_llm import perplexity_search
except Exception:
    perplexity_search = None  # type: ignore
try:
    # Optional; used in other flows; not required for simple search comparisons
    from llm import chat_once as _chat_once_impl, extract_contact_info as _extract_contact_info_impl
    chat_once = _chat_once_impl  # type: ignore[assignment]
    extract_contact_info = _extract_contact_info_impl  # type: ignore[assignment]
except Exception:
    from typing import Any as _Any
    from typing import Optional as _Optional
    from typing import Dict as _Dict
    def chat_once(*args: _Any, **kwargs: _Any) -> str:  # type: ignore[no-redef]
        return ""
    def extract_contact_info(*args: _Any, **kwargs: _Any) -> _Dict[str, _Optional[str]]:  # type: ignore[no-redef]
        return {"email": None, "phone": None}


def find_contact_info_simple(company_name: str, country: Optional[str] = None) -> None:
    """
    Simplified version for debugging Google search.
    """
    search_term = f"{company_name} {country}" if country else company_name
    # Target contact page information explicitly (email/phone)
    search_query = (
        f"{search_term} (contact page OR 'contact us' OR contacts) "
        f"(email OR e-mail) (phone OR telephone OR tel)"
    )
    
    print(f"DEBUG: Company: {company_name}")
    print(f"DEBUG: Country: {country}")
    print(f"DEBUG: Search term: {search_term}")
    print(f"DEBUG: Search query: {search_query}")
    print(f"DEBUG: About to call google_search...")
    
    try:
        results = google_search(search_query, n=5, print_results=True)
        print(f"DEBUG: Google search returned: {type(results)}")
        print(f"DEBUG: Number of results: {len(results) if results else 0}")
        if results:
            print(f"DEBUG: First result keys: {list(results[0].keys())}")
    except Exception as e:
        print(f"DEBUG: Error calling google_search: {e}")
        print(f"DEBUG: Error type: {type(e)}")
        import traceback
        traceback.print_exc()


def find_contact_info_simple_google_search(company_name: str, country: Optional[str] = None, n: int = 5) -> List[Dict]:
    """Return Google Custom Search results as Sources-like list.

    Each item: {title, url, snippet, engine: 'google'}
    """
    search_term = f"{company_name} {country}" if country else company_name
    # Emphasize direct contact info discovery
    search_query = (
        f"{search_term} (contact page OR 'contact us' OR contacts) "
        f"(email OR e-mail) (phone OR telephone OR tel)"
    )
    items = google_search(search_query, n=n, print_results=False)
    sources: List[Dict] = []
    for it in items:
        sources.append({
            "title": it.get("title"),
            "url": it.get("link") or it.get("formattedUrl"),
            "snippet": it.get("snippet"),
            "engine": "google"
        })
    return sources


def find_contact_info_simple_openai(company_name: str, country: Optional[str] = None, n: int = 5) -> List[Dict]:
    """Use OpenAI web search wrapper and return sources."""
    if openai_web_search is None:
        return []
    search_term = f"{company_name} {country}" if country else company_name
    # Ask for official contact page with email/phone explicitly
    query = (
        f"{search_term} official website (contact page OR 'contact us' OR contacts) "
        f"(email OR e-mail) (phone OR telephone OR tel)"
    )
    return openai_web_search(query)[:n]


def find_contact_info_simple_perplexity(company_name: str, country: Optional[str] = None, n: int = 5) -> List[Dict]:
    """Use Perplexity wrapper and return sources."""
    if perplexity_search is None:
        return []
    search_term = f"{company_name} {country}" if country else company_name
    query = (
        f"{search_term} official website (contact page OR 'contact us' OR contacts) "
        f"(email OR e-mail) (phone OR telephone OR tel)"
    )
    return perplexity_search(query)[:n]


def compare_search_engines(company_name: str, country: Optional[str] = None, n: int = 5) -> Dict[str, List[Dict]]:
    """Return a dict with sources from all three engines for side-by-side comparison."""
    result: Dict[str, List[Dict]] = {
        "google": [],
        "openai": [],
        "perplexity": [],
    }
    try:
        result["google"] = find_contact_info_simple_google_search(company_name, country, n=n)
    except Exception:
        pass
    try:
        result["openai"] = find_contact_info_simple_openai(company_name, country, n=n)
    except Exception:
        pass
    try:
        result["perplexity"] = find_contact_info_simple_perplexity(company_name, country, n=n)
    except Exception:
        pass
    return result


if __name__ == "__main__":
    # Simple comparison run
    company = "1875 Finance"
    country = "Switzerland"
    print("=== SEARCH ENGINES COMPARISON ===")
    print(f"Company: {company} | Country: {country}")

    try:
        g_sources = find_contact_info_simple_google_search(company, country, n=5)
    except Exception as e:
        g_sources = []
        print(f"Google error: {e}")

    try:
        o_sources = find_contact_info_simple_openai(company, country, n=5)
    except Exception as e:
        o_sources = []
        print(f"OpenAI error: {e}")

    try:
        p_sources = find_contact_info_simple_perplexity(company, country, n=5)
    except Exception as e:
        p_sources = []
        print(f"Perplexity error: {e}")

    def _print_sources(name: str, sources):
        print(f"\n{name} sources: {len(sources)}")
        for i, s in enumerate(sources[:5], 1):
            print(f"  {i}. {s.get('title') or ''}")
            print(f"     {s.get('url')}")
            snip = s.get('snippet') or ''
            if snip:
                print(f"     {snip[:140]}{'...' if len(snip)>140 else ''}")

    _print_sources("Google", g_sources)
    _print_sources("OpenAI", o_sources)
    _print_sources("Perplexity", p_sources)

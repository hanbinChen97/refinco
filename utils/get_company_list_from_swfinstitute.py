"""
Utilities: get_company_list_from_swfinstitute

Goal (per plan.md):
- Request the SWF Institute wealth manager listing page HTML,
- Feed the relevant "list-group list-group-wrap" section to GPT-4.1 via Azure OpenAI,
- Extract all company names and country names on the page into a list.

Public API:
- get_company_list_from_swfinstitute(url: str) -> list[dict]
  Returns: [{"company_name": str, "country": str | None}, ...]

Notes:
- Keeps the prompt strict to ensure valid JSON. Falls back to a simple
  BeautifulSoup-based parse if the LLM returns invalid JSON or empty results.
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# Ensure .env is loaded via utils package initializer if available
try:
    import utils  # noqa: F401
except Exception:
    pass

# Lazy import to avoid crashing when Azure OpenAI env vars are missing at import time
def _get_chat_once():
    try:
        from utils.llm import chat_once  # type: ignore
        return chat_once
    except Exception:
        return None


def _extract_target_html(html: str) -> str:
    """Extract the target container's HTML to keep token usage small.

    Looks for elements with class 'list-group list-group-wrap'. If not found,
    returns the original HTML (LLM will still try its best).
    """
    try:
        soup = BeautifulSoup(html, "lxml")
        blocks = soup.select(".list-group.list-group-wrap")
        if not blocks:
            return html
        # Concatenate all relevant blocks' HTML
        return "\n\n".join(str(b) for b in blocks)
    except Exception:
        return html


def _llm_json(system_message: str, user_message: str, *, temperature: float = 0.0, max_tokens: int = 600) -> Dict:
    """Call LLM and parse JSON; if it fails, return empty dict."""
    chat_once = _get_chat_once()
    if chat_once is None:
        return {}
    try:
        resp = chat_once(system_message, user_message, temperature=temperature, max_tokens=max_tokens)
        text = (resp or "").strip()
        if text.startswith("```"):
            # remove fences
            text = text.strip("`\n ")
            if text.startswith("json"):
                text = text[4:].lstrip("\n")
        return json.loads(text)
    except Exception:
        return {}


def _fallback_parse(html: str) -> List[Dict[str, Optional[str]]]:
    """Heuristic fallback parser when LLM fails: try to read company and country
    from visible card/list items under the container.
    """
    out: List[Dict[str, Optional[str]]] = []
    try:
        soup = BeautifulSoup(html, "lxml")
        blocks = soup.select(".list-group.list-group-wrap") or [soup]
        for block in blocks:
            # Common patterns: each item may be an <a> or <div> with inner headings/spans
            for item in block.select(".list-group-item, li, a, .card, .media"):
                text = item.get_text(" ", strip=True)
                if not text:
                    continue
                # Very rough split: often formatted like "Company Name – Country" or includes country as a trailing label
                company: Optional[str] = None
                country: Optional[str] = None

                # Try micro-structure first
                name_el = item.select_one("h3, h4, .title, .company, .name")
                country_el = item.select_one(".country, .badge, .label, small")
                if name_el:
                    company = name_el.get_text(" ", strip=True) or None
                if country_el:
                    country = country_el.get_text(" ", strip=True) or None

                # Fallback: use delimiters
                if not company:
                    parts = [p.strip() for p in text.split(" – ")]
                    if len(parts) >= 2:
                        company, country = parts[0], parts[-1]
                    else:
                        # Last attempt: take first sentence as company
                        company = text.split("|")[0].split("-")[0].strip()

                if company:
                    out.append({"company_name": company, "country": country})
    except Exception:
        pass
    return out


def get_company_list_from_swfinstitute(url: str, *, timeout: int = 20) -> List[Dict[str, Optional[str]]]:
    """Fetch a SWF Institute listing page and extract company + country via LLM.

    Args:
        url: Page URL, e.g.,
             https://dev.swfinstitute.org/profiles/wealth-manager/europe
        timeout: HTTP timeout seconds.

    Returns:
        A list of dicts: [{"company_name": str, "country": str | None}, ...]
    """
    start_time = time.time()
    print(f"    Fetching page: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    request_start = time.time()
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    html = resp.text
    request_time = time.time() - request_start
    print(f"      HTTP request completed in {request_time:.2f}s")

    target_html = _extract_target_html(html)

    system_message = (
        "You are a data parser. Extract company names and countries from wealth manager listings.\n"
        "Return ONLY JSON: {\"companies\": [{\"company_name\": \"...\", \"country\": \"...\"}]}\n"
        "\n"
        "CRITICAL: Each entry contains text like 'Company Name Wealth Manager in Country, Region'\n"
        "Your task: Split this text at ' Wealth Manager in ' OR ' Family Office in '\n"
        "- company_name = text BEFORE the split point\n"
        "- country = text AFTER the split point\n"
        "\n"
        "EXACT transformations required:\n"
        "'Alpha Blue Ocean Wealth Manager in France, Europe' → {\"company_name\": \"Alpha Blue Ocean\", \"country\": \"France, Europe\"}\n"
        "'Amadeus Capital SA Wealth Manager in Switzerland, Europe' → {\"company_name\": \"Amadeus Capital SA\", \"country\": \"Switzerland, Europe\"}\n"
        "\n"
        "DO NOT include 'Wealth Manager' or 'Family Office' in either field.\n"
        "Return only valid JSON, no other text."
    )
    user_message = (
        "Extract companies from this HTML. Split each entry on 'Wealth Manager in' or 'Family Office in' patterns.\n\n"
        + target_html
    )

    llm_start = time.time()
    print(f"      Calling LLM for extraction...")
    data = _llm_json(system_message, user_message, temperature=0.0, max_tokens=700)
    llm_time = time.time() - llm_start
    print(f"      LLM call completed in {llm_time:.2f}s")
    companies = []
    if isinstance(data, dict):
        raw = data.get("companies")
        if isinstance(raw, list):
            for it in raw:
                if isinstance(it, dict):
                    name = it.get("company_name")
                    country = it.get("country")
                    if isinstance(name, str) and name.strip():
                        # Apply aggressive post-processing to fix LLM extraction
                        def clean_text_split(text: str) -> tuple[str, str]:
                            """Split text on business descriptors and return (company, country)."""
                            text = text.strip()
                            
                            # Try splitting on various patterns
                            split_patterns = [
                                " Wealth Manager in ",
                                " Family Office in ",
                                " Asset Manager in ",
                                " Private Bank in ",
                                " Investment Manager in "
                            ]
                            
                            for pattern in split_patterns:
                                if pattern in text:
                                    parts = text.split(pattern, 1)
                                    if len(parts) == 2:
                                        return parts[0].strip(), parts[1].strip()
                            
                            # Fallback: if no split pattern found, try to extract from the end
                            if " in " in text:
                                # Look for country patterns at the end
                                parts = text.rsplit(" in ", 1)
                                if len(parts) == 2:
                                    company_part = parts[0].strip()
                                    country_part = parts[1].strip()
                                    
                                    # Remove business descriptors from company name
                                    for desc in ["Wealth Manager", "Family Office", "Asset Manager", "Private Bank"]:
                                        if company_part.endswith(desc):
                                            company_part = company_part[:-len(desc)].strip()
                                            break
                                    
                                    return company_part, country_part
                            
                            # Last resort: return as is
                            return text, ""
                        
                        # Clean the extracted data
                        raw_name = name.strip()
                        raw_country = country.strip() if isinstance(country, str) else ""
                        
                        # If name contains patterns, try to split it
                        clean_name, extracted_country = clean_text_split(raw_name)
                        
                        # Use extracted country if we found one, otherwise use the provided country
                        final_country = extracted_country if extracted_country else raw_country
                        
                        # Clean up the final country field
                        if final_country:
                            # Remove any remaining business descriptors
                            for desc in ["Wealth Manager in", "Wealth Manager", "Family Office in", "Family Office", "Asset Manager in", "Asset Manager"]:
                                if final_country.startswith(desc):
                                    final_country = final_country.replace(desc, "").strip()
                            
                            # Remove leading/trailing 'in'
                            final_country = final_country.strip().lstrip("in").strip()
                        
                        companies.append({
                            "company_name": clean_name,
                            "country": final_country if final_country else None,
                        })

    # Fallback if LLM failed or returned nothing
    if not companies:
        print(f"      LLM returned no results, using fallback parser...")
        raw_companies = _fallback_parse(target_html or html)
        
        # Apply the same post-processing to fallback results
        for raw_company in raw_companies:
            raw_name = (raw_company.get("company_name") or "").strip()
            raw_country = (raw_company.get("country") or "").strip()
            
            if raw_name:
                # Use the same cleaning logic
                def clean_text_split(text: str) -> tuple[str, str]:
                    """Split text on business descriptors and return (company, country)."""
                    text = text.strip()
                    
                    # Try splitting on various patterns
                    split_patterns = [
                        " Wealth Manager in ",
                        " Family Office in ",
                        " Asset Manager in ",
                        " Private Bank in ",
                        " Investment Manager in "
                    ]
                    
                    for pattern in split_patterns:
                        if pattern in text:
                            parts = text.split(pattern, 1)
                            if len(parts) == 2:
                                return parts[0].strip(), parts[1].strip()
                    
                    # Fallback: if no split pattern found, try to extract from the end
                    if " in " in text:
                        # Look for country patterns at the end
                        parts = text.rsplit(" in ", 1)
                        if len(parts) == 2:
                            company_part = parts[0].strip()
                            country_part = parts[1].strip()
                            
                            # Remove business descriptors from company name
                            for desc in ["Wealth Manager", "Family Office", "Asset Manager", "Private Bank"]:
                                if company_part.endswith(desc):
                                    company_part = company_part[:-len(desc)].strip()
                                    break
                            
                            return company_part, country_part
                    
                    # Last resort: return as is
                    return text, ""
                
                clean_name, extracted_country = clean_text_split(raw_name)
                final_country = extracted_country if extracted_country else raw_country
                
                # Clean up the final country field
                if final_country:
                    # Remove any remaining business descriptors
                    for desc in ["Wealth Manager in", "Wealth Manager", "Family Office in", "Family Office", "Asset Manager in", "Asset Manager"]:
                        if final_country.startswith(desc):
                            final_country = final_country.replace(desc, "").strip()
                    
                    # Remove leading/trailing 'in'
                    final_country = final_country.strip().lstrip("in").strip()
                
                companies.append({
                    "company_name": clean_name,
                    "country": final_country if final_country else None,
                })

    total_time = time.time() - start_time
    print(f"    Extracted {len(companies)} companies in {total_time:.2f}s")
    return companies


if __name__ == "__main__":
    # Simple smoke test across first 3 pages from plan.md
    pages = [
        "https://dev.swfinstitute.org/profiles/wealth-manager/europe",
        "https://dev.swfinstitute.org/profiles/wealth-manager/europe?page=2",
        "https://dev.swfinstitute.org/profiles/wealth-manager/europe?page=3",
    ]
    all_rows: List[Dict[str, Optional[str]]] = []
    for i, p in enumerate(pages, 1):
        try:
            page_start = time.time()
            print(f"\nFetching page {i}/{len(pages)}...")
            rows = get_company_list_from_swfinstitute(p)
            page_time = time.time() - page_start
            print(f"Page {i} completed: {len(rows)} companies in {page_time:.2f}s")
            all_rows.extend(rows)
        except Exception as e:
            print(f"Error fetching page {i} ({p}): {e}")

    # Preview a few
    for r in all_rows[:10]:
        print(r)

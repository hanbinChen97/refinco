"""
Utilities for selecting likely official websites and extracting contact info.

Exports:
- llm_select_most_likely_website(url_candidates: list[str], company: str) -> str
- llm_extract_contact_info(url: str) -> tuple[str | None, str | None, str | None]

Uses heuristics first and can optionally leverage Azure OpenAI via llm.py
if the environment is configured. Falls back gracefully when LLM is not
available.
"""
from __future__ import annotations

import re
import sys
from typing import Iterable, List, Optional, Tuple, cast
from urllib.parse import urljoin, urlparse

import requests
try:
    import tldextract  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - optional dependency fallback
    tldextract = None  # type: ignore[assignment]

from bs4 import BeautifulSoup, Tag

# Optional LLM import
def _get_llm():
    try:
        import llm  # local module
        return llm
    except Exception:
        return None


REQUEST_TIMEOUT = 15
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    )
}

BLOCKLIST_DOMAINS = {
    "linkedin.com",
    "x.com",
    "twitter.com",
    "facebook.com",
    "instagram.com",
    "bloomberg.com",
    "crunchbase.com",
    "wikipedia.org",
    "rocketreach.co",
    "pitchbook.com",
    "reuters.com",
    "ft.com",
    "glassdoor",
    "yelp.com",
    "opencorporates.com",
    "companieshouse.gov.uk",
    "sec.gov",
    "gov.uk",
}

CONTACT_KEYWORDS = [
    "contact", "contacts", "contact-us", "kontakt", "contatti", "contacto",
    "impressum", "contactez", "kontact", "kontakta", "contato", "kontaktai",
]

ADDRESS_HINTS = [
    "address", "adresse", "indirizzo", "dirección", "direccio", "anschrift",
    "addresse", "ubicación", "ubicacion", "location"
]

STREET_WORDS = [
    "street", "st.", "st ", "road", "rd", "avenue", "ave", "blvd", "way", "lane", "ln",
    "court", "ct", "place", "pl", "drive", "dr", "square", "sq", "highway", "hwy",
    "rue", "chemin", "allee", "allée", "cours", "chaussée", "via", "viale", "piazza",
    "calle", "camino", "strasse", "straße", "platz"
]

EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s-]?)?(?:\(\d{1,4}\)[\s-]?)?(?:\d[\s-]?){6,15}\d"
)
POSTAL_RE = re.compile(r"\b\d{4,6}\b")


def _registered_domain(host: str) -> str:
    if tldextract is not None:
        ext = tldextract.extract(host)
        if not ext.domain and not ext.suffix:
            return host.lower()
        reg = ".".join(p for p in [ext.domain, ext.suffix] if p)
        return reg.lower()
    # Fallback: take last 2 labels as a naive registered domain
    parts = host.lower().split(".")
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return host.lower()


def _tokenize_company(name: str) -> List[str]:
    tokens = re.split(r"[^a-z0-9]+", name.lower())
    return [t for t in tokens if t and t not in {"the", "group", "sa", "ag", "ltd", "limited", "inc"}]


def llm_select_most_likely_website(url_candidates: List[str], company: str) -> str:
    """Pick the most likely official website from displayLink-like domains or URLs."""
    if not url_candidates:
        return ""

    tokens = _tokenize_company(company)

    def score(candidate: str) -> Tuple[int, str]:
        # Accept domains or full URLs
        host = urlparse("https://" + candidate if "://" not in candidate else candidate).netloc or candidate
        reg = _registered_domain(host)
        s = 0
        if any(b in reg for b in BLOCKLIST_DOMAINS):
            s -= 100
        # token match bonus
        for t in tokens:
            if t and t in reg:
                s += 5
        # short domain bonus
        s += max(0, 15 - len(reg)) // 3
        # prefer non-www
        if host.startswith("www."):
            s -= 1
        return s, reg

    ranked = sorted(url_candidates, key=lambda c: score(c), reverse=True)
    best = ranked[0]
    # Normalize to https://<registered_domain>
    host = urlparse("https://" + best if "://" not in best else best).netloc or best
    reg = _registered_domain(host)
    return f"https://{reg}"


def llm_select_most_likely_contact_page(url_candidates: List[str], company: str) -> str:
    """Pick the most likely contact page from a list of full URLs.

    Heuristics:
    - Prefer URLs containing contact keywords (contact, kontakt, impressum, etc.)
    - Prefer domains that seem to match company tokens
    - Penalize known non-official domains (social, media, directories)
    - Prefer HTTPS and shorter URLs
    """
    if not url_candidates:
        return ""

    tokens = _tokenize_company(company)

    def score(u: str) -> Tuple[int, str, int]:
        try:
            pu = urlparse(u if "://" in u else f"https://{u}")
        except Exception:
            pu = urlparse("")
        host = pu.netloc or u
        reg = _registered_domain(host)
        path = pu.path.lower()
        s = 0

        # Prefer contact keywords in path
        if any(k in path for k in CONTACT_KEYWORDS):
            s += 20

        # Penalize blocklisted domains
        if any(b in reg for b in BLOCKLIST_DOMAINS):
            s -= 50

        # Token match bonus on domain
        for t in tokens:
            if t and t in reg:
                s += 5

        # HTTPS preference
        if (pu.scheme or "").lower() == "https":
            s += 2

        # Shorter URL bonus (up to a point)
        s += max(0, 60 - len(u)) // 10

        # Prefer pages that look like /contact or /contact-us exactly
        if path.rstrip("/") in {"/contact", "/contact-us", "/kontakt", "/contacts", "/impressum"}:
            s += 5

        return s, reg, -len(u)

    best = sorted(url_candidates, key=lambda u: score(u), reverse=True)[0]
    return best


def _fetch(url: str) -> Optional[str]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _find_contact_pages(base_url: str, html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a_node in soup.find_all("a", href=True):
        a = cast(Tag, a_node)
        text = (a.get_text(" ", strip=True) or "").lower()
        href_val = a.get("href") or ""
        href = str(href_val)
        href_l = href.lower()
        if any(k in href_l for k in CONTACT_KEYWORDS) or any(k in text for k in CONTACT_KEYWORDS):
            links.append(urljoin(base_url, href))
    # De-dup while preserving order
    seen = set()
    out = []
    for u in links:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _extract_text_fields(html: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)

    email = None
    m = EMAIL_RE.search(text)
    if m:
        email = m.group(0)

    phone = None
    # Try to avoid matching long numbers that might be IBANs or VAT etc by simple heuristic
    for m in PHONE_RE.finditer(text):
        cand = m.group(0)
        # filter out implausible sequences (e.g., 16+ digits when removing separators)
        if len(re.sub(r"\D", "", cand)) <= 15:
            phone = cand
            break

    address = None
    # Look for <address> tag first
    addr_tag = soup.find("address")
    if addr_tag:
        address = addr_tag.get_text(" ", strip=True)
    if not address:
        # heuristic: find lines with a street word and a postal code nearby
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            low = ln.lower()
            if any(sw in low for sw in STREET_WORDS):
                # include neighboring lines to capture city/postal
                window = " ".join(lines[i:i+3])
                if POSTAL_RE.search(window) or any(h in low for h in ADDRESS_HINTS):
                    address = window.strip()
                    break
    return email, phone, address


def llm_extract_contact_info(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Fetch the site and its likely contact page to extract email, phone, address.

    Returns: (email, phone, address) — any can be None if not found.
    """
    if not url:
        return None, None, None

    # Normalize base
    p = urlparse(url)
    base = f"{p.scheme or 'https'}://{p.netloc}" if p.netloc else url

    # 1) Fetch homepage
    home_html = _fetch(base)
    if not home_html:
        # try original url if different
        if url != base:
            home_html = _fetch(url)
    if not home_html:
        return None, None, None

    # 2) Try contact pages
    contact_urls = _find_contact_pages(base, home_html)
    # Prioritize URLs containing 'contact' first
    contact_urls = sorted(contact_urls, key=lambda u: ("contact" not in u.lower(), len(u)))

    candidates_html = []
    for cu in contact_urls[:3]:  # limit
        h = _fetch(cu)
        if h:
            candidates_html.append(h)

    # 3) Extract from contact page(s) then homepage
    for h in candidates_html + [home_html]:
        email, phone, address = _extract_text_fields(h)
        if any([email, phone, address]):
            return email, phone, address

    # Optional: last resort LLM extraction
    llm_mod = _get_llm()
    if llm_mod:
        try:
            content = (candidates_html[0] if candidates_html else home_html)[:40_000]
            prompt = (
                "Extract a single best email, international phone number, and postal address "
                "from the following HTML/text. Reply as JSON with keys email, phone, address.\n\n" + content
            )
            reply = llm_mod.chat_once(
                "You are an information extraction assistant.",
                prompt,
                temperature=0.1,
                max_tokens=300,
            )
            # very light parsing
            m_email = re.search(EMAIL_RE, reply or "")
            m_phone = re.search(PHONE_RE, reply or "")
            # address: take the longest line containing a street word
            addr = None
            lines = [ln.strip() for ln in (reply or "").splitlines() if ln.strip()]
            cand_lines = [ln for ln in lines if any(sw in ln.lower() for sw in STREET_WORDS)]
            if cand_lines:
                addr = max(cand_lines, key=len)
            return (m_email.group(0) if m_email else None,
                    m_phone.group(0) if m_phone else None,
                    addr)
        except Exception:
            pass

    return None, None, None

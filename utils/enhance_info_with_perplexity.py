"""
Enhance company info with Perplexity API.

Public API:
- enhance_company_info_with_perplexity(companies: list[dict]) -> list[dict]

Input items should include:
- {"company_name": str, "country": str | None}

Output items include unified keys (aligned with company_query_compare.py composite):
- company_name, country,
- company_email, company_phone, company_contact_page,
- ceo, ceo_email, ceo_phone,
- cofounder, cofounder_email, cofounder_phone
"""

from __future__ import annotations

import json
import os
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv, find_dotenv

# Load environment variables early so __main__ checks see them even if the
# perplexity_llm import path handling fails. We try the standard search first
# and then fall back to the repository root (parent of this file's folder).
_loaded = load_dotenv(find_dotenv())
if not os.getenv("PERPLEXITY_API_KEY"):
	_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
	_env_path = os.path.join(_project_root, ".env")
	if os.path.exists(_env_path):
		load_dotenv(_env_path)

# Allow running this file directly (python utils/enhance_info_with_perplexity.py)
# by ensuring the project root is on sys.path so 'utils' resolves as a package.
if __name__ == "__main__" and __package__ is None:
	import sys as _sys
	_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
	if _project_root not in _sys.path:
		_sys.path.insert(0, _project_root)

from utils.perplexity_llm import perplexity_generate_text  # type: ignore


COMPOSITE_KEYS = [
	"company_name",
	"country",
	"ceo",
	"company_email",
	"company_contact_page",
	"company_phone",
	"ceo_email",
	"ceo_phone",
	"cofounder",
	"cofounder_email",
	"cofounder_phone",
]


def _safe_json_loads(text: str) -> Dict:
	text = (text or "").strip()
	if text.startswith("```"):
		# strip fences like ```json ... ```
		text = text.strip("`\n ")
		if text.startswith("json"):
			text = text[4:].lstrip("\n")
	try:
		return json.loads(text)
	except Exception:
		return {}


def _ppx_call(prompt: str, *, model: Optional[str] = None) -> Dict:
	if perplexity_generate_text is None:
		return {}
	model = model or os.getenv("PERPLEXITY_MODEL", "sonar-pro")
	try:
		res = perplexity_generate_text(prompt, model=model)  # type: ignore[call-arg]
		text = (res or {}).get("text", "")
		return _safe_json_loads(text)
	except Exception:
		return {}


def _ppx_contact(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
	prompt = f"""
You are an information extraction agent. Search the web and find the official company contact information (not individuals) for this company.

Company: {company}
Country: {country or ''}

Return STRICT JSON with exactly these keys and nothing else:
{{
  "company_email": string | null,
  "company_phone": string | null,
  "company_contact_page": string | null
}}

Rules:
- Prefer official sources. If unknown, use null. One primary value per field.
- Respond with JSON only. No markdown.
""".strip()
	data = _ppx_call(prompt)
	def _get(d: Dict, k: str) -> Optional[str]:
		v = d.get(k) if isinstance(d, dict) else None
		return v if isinstance(v, str) or v is None else None
	return {
		"company_email": _get(data, "company_email"),
		"company_phone": _get(data, "company_phone"),
		"company_contact_page": _get(data, "company_contact_page"),
	}


def _ppx_management(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
	prompt = f"""
You are an information extraction agent. Search the web and find management info (CEO and Co-founder) for this company and their public contact details if available.

Company: {company}
Country: {country or ''}

Return STRICT JSON with exactly these keys and nothing else:
{{
  "ceo": string | null,
  "ceo_email": string | null,
  "ceo_phone": string | null,
  "cofounder": string | null,
  "cofounder_email": string | null,
  "cofounder_phone": string | null
}}

Rules:
- Only extract if clearly attributable to this company; otherwise use null.
- Respond with JSON only. No markdown.
""".strip()
	data = _ppx_call(prompt)
	def _get(d: Dict, k: str) -> Optional[str]:
		v = d.get(k) if isinstance(d, dict) else None
		return v if isinstance(v, str) or v is None else None
	return {
		"ceo": _get(data, "ceo") or _get(data, "CEO"),
		"ceo_email": _get(data, "ceo_email"),
		"ceo_phone": _get(data, "ceo_phone"),
		"cofounder": _get(data, "cofounder") or _get(data, "co_founder"),
		"cofounder_email": _get(data, "cofounder_email"),
		"cofounder_phone": _get(data, "cofounder_phone"),
	}


def _merge_single_results(company: str, country: Optional[str], contact: Dict[str, Optional[str]], mgmt: Dict[str, Optional[str]]) -> Dict[str, Optional[str]]:
	return {
		"company_name": company,
		"country": country or "",
		"ceo": (mgmt.get("ceo") if mgmt else None),
		"company_email": (contact.get("company_email") if contact else None),
		"company_contact_page": (contact.get("company_contact_page") if contact else None),
		"company_phone": (contact.get("company_phone") if contact else None),
		"ceo_email": (mgmt.get("ceo_email") if mgmt else None),
		"ceo_phone": (mgmt.get("ceo_phone") if mgmt else None),
		"cofounder": (mgmt.get("cofounder") if mgmt else None),
		"cofounder_email": (mgmt.get("cofounder_email") if mgmt else None),
		"cofounder_phone": (mgmt.get("cofounder_phone") if mgmt else None),
	}


def enhance_company_info_with_perplexity(companies: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
	"""Enrich a list of companies using Perplexity web-enabled model.

	Args:
		companies: List of {company_name: str, country: str | None}

	Returns:
		List of rows with the composite keys as fields.
	"""
	results: List[Dict[str, Optional[str]]] = []
	total_companies = len(companies)
	for i, item in enumerate(companies, 1):
		name = (item or {}).get("company_name")
		if not isinstance(name, str) or not name.strip():
			continue
		country = (item or {}).get("country")
		
		company_start = time.time()
		print(f"  Processing company {i}/{total_companies}: {name.strip()}...")
		
		c = _ppx_contact(name.strip(), country if isinstance(country, str) else None)
		m = _ppx_management(name.strip(), country if isinstance(country, str) else None)
		row = _merge_single_results(name.strip(), country if isinstance(country, str) else None, c, m)
		results.append(row)
		
		company_time = time.time() - company_start
		print(f"    Completed in {company_time:.2f}s")
	return results


if __name__ == "__main__":
	# Smoke test: run against a tiny sample (requires PERPLEXITY_API_KEY)
	if not os.getenv("PERPLEXITY_API_KEY"):
		print("SKIP: PERPLEXITY_API_KEY not set; populate .env or environment to test.")
	else:
		sample: List[Dict[str, Optional[str]]] = [
			{"company_name": "Rothschild & Co", "country": "France"},
			{"company_name": "UBS", "country": "Switzerland"},
		]
		enriched = enhance_company_info_with_perplexity(sample)
		for r in enriched:
			print(json.dumps(r, ensure_ascii=False))


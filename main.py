"""
Workflow runner: 
- Fetch wealth manager companies from SWF Institute, 
- enhance via Perplexity, and export CSV.

Workflow (per plan.md):
1) Request the target listing pages and extract (companies + countries) using Azure OpenAI.
2) For the first N companies, call Perplexity to enrich (contact + management) fields.
3) Write a CSV with unified columns.
"""

from __future__ import annotations
import csv
import datetime as dt
import os
import time
from typing import Dict, List, Optional

# Local utilities
from utils.get_company_list_from_swfinstitute import (
	get_company_list_from_swfinstitute,
)
from utils.enhance_info_with_perplexity import (
	enhance_company_info_with_perplexity,
	COMPOSITE_KEYS,
)


def _default_output_path() -> str:
	ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
	out_dir = os.path.join(os.path.dirname(__file__), "data")
	os.makedirs(out_dir, exist_ok=True)
	return os.path.join(out_dir, f"wealth_managers_europe_{ts}.csv")


def _build_urls(base_url: str, pages: int) -> List[str]:
	pages = max(1, pages)
	urls = [base_url]
	for p in range(2, pages + 1):
		sep = "&" if "?" in base_url else "?"
		urls.append(f"{base_url}{sep}page={p}")
	return urls


def _unique_by_company(items: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
	seen = set()
	out = []
	for it in items:
		name = (it or {}).get("company_name")
		key = name.strip().lower() if isinstance(name, str) else None
		if not key or key in seen:
			continue
		seen.add(key)
		out.append(it)
	return out


def run(base_url: str, pages: int, limit: int, enhance: bool, output_path: str) -> str:
	# 1) Collect companies from pages
	print("Step 1: Collecting companies from pages...")
	step1_start = time.time()
	urls = _build_urls(base_url, pages)
	all_companies: List[Dict[str, Optional[str]]] = []
	for u in urls:
		try:
			rows = get_company_list_from_swfinstitute(u)
		except Exception as e:
			print(f"Error fetching {u}: {e}")
			rows = []
		all_companies.extend(rows)

	all_companies = _unique_by_company(all_companies)
	step1_time = time.time() - step1_start
	print(f"Collected {len(all_companies)} unique companies from {len(urls)} page(s). (took {step1_time:.2f}s)")

	# 2) Take first N
	limit = max(0, limit)
	selected = all_companies[:limit] if limit else all_companies
	print(f"Selected {len(selected)} companies for processing.")

	# 3) Enhance with Perplexity (optional)
	if enhance and selected:
		print("Step 2: Enhancing with Perplexity...")
		step2_start = time.time()
		api_set = bool(os.getenv("PERPLEXITY_API_KEY"))
		if not api_set:
			print("Warning: PERPLEXITY_API_KEY is not set. Enhancement may yield empty fields.")
		try:
			selected = enhance_company_info_with_perplexity(selected)
			step2_time = time.time() - step2_start
			print(f"Enhancement completed. (took {step2_time:.2f}s)")
		except Exception as e:
			step2_time = time.time() - step2_start
			print(f"Enhancement error: {e}. Proceeding with base fields only. (took {step2_time:.2f}s)")

	# 4) Write CSV
	print("Step 3: Writing CSV...")
	step3_start = time.time()
	os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

	# Ensure all rows contain the same keys in COMPOSITE_KEYS order
	prepared_rows: List[Dict[str, str]] = []
	for row in selected:
		r: Dict[str, str] = {}
		for key in COMPOSITE_KEYS:
			val = row.get(key) if isinstance(row, dict) else None
			r[key] = "" if val is None else str(val)
		prepared_rows.append(r)

	with open(output_path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=COMPOSITE_KEYS)
		writer.writeheader()
		writer.writerows(prepared_rows)

	step3_time = time.time() - step3_start
	print(f"Wrote {len(prepared_rows)} rows to: {output_path} (took {step3_time:.2f}s)")
	return output_path


def main():
	"""Programmatic runner without CLI.

	Defaults:
	- base_urls: SWF Institute Europe and Asia wealth manager listings
	- pages: 3
	- limit: 20 (per user request "先输出前20 company")
	- enhance: True (use Perplexity if available)
	- output: data/wealth_managers_combined_<timestamp>.csv
	"""
	print("Starting wealth manager data collection workflow...")
	total_start = time.time()
	
	base_urls = [
		"https://dev.swfinstitute.org/profiles/wealth-manager/europe",
		"https://dev.swfinstitute.org/profiles/wealth-manager/asia"
	]
	pages = 3
	limit = 0  # 0 means no limit - output all companies
	enhance = True  # Enable Perplexity enhancement
	
	# Combine data from both regions
	all_companies: List[Dict[str, Optional[str]]] = []
	
	for base_url in base_urls:
		region = "Europe" if "europe" in base_url else "Asia"
		print(f"\nProcessing {region} region...")
		
		# Collect companies from pages
		print(f"Step 1: Collecting companies from {region} pages...")
		step1_start = time.time()
		urls = _build_urls(base_url, pages)
		region_companies: List[Dict[str, Optional[str]]] = []
		for u in urls:
			try:
				rows = get_company_list_from_swfinstitute(u)
			except Exception as e:
				print(f"Error fetching {u}: {e}")
				rows = []
			region_companies.extend(rows)
		
		step1_time = time.time() - step1_start
		print(f"Collected {len(region_companies)} companies from {region}. (took {step1_time:.2f}s)")
		all_companies.extend(region_companies)
	
	# Remove duplicates across all regions
	all_companies = _unique_by_company(all_companies)
	print(f"\nTotal unique companies across all regions: {len(all_companies)}")
	
	# Take first N
	limit = max(0, limit)
	selected = all_companies[:limit] if limit else all_companies
	print(f"Selected {len(selected)} companies for processing.")
	
	# Enhance with Perplexity (optional)
	if enhance and selected:
		print("Step 2: Enhancing with Perplexity...")
		step2_start = time.time()
		api_set = bool(os.getenv("PERPLEXITY_API_KEY"))
		if not api_set:
			print("Warning: PERPLEXITY_API_KEY is not set. Enhancement may yield empty fields.")
		try:
			selected = enhance_company_info_with_perplexity(selected)
			step2_time = time.time() - step2_start
			print(f"Enhancement completed. (took {step2_time:.2f}s)")
		except Exception as e:
			step2_time = time.time() - step2_start
			print(f"Enhancement error: {e}. Proceeding with base fields only. (took {step2_time:.2f}s)")
	
	# Write CSV
	print("Step 3: Writing CSV...")
	step3_start = time.time()
	ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
	out_dir = os.path.join(os.path.dirname(__file__), "data")
	os.makedirs(out_dir, exist_ok=True)
	output_path = os.path.join(out_dir, f"wealth_managers_combined_{ts}.csv")
	
	os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

	# Ensure all rows contain the same keys in COMPOSITE_KEYS order
	prepared_rows: List[Dict[str, str]] = []
	for row in selected:
		r: Dict[str, str] = {}
		for key in COMPOSITE_KEYS:
			val = row.get(key) if isinstance(row, dict) else None
			r[key] = "" if val is None else str(val)
		prepared_rows.append(r)

	with open(output_path, "w", newline="", encoding="utf-8") as f:
		writer = csv.DictWriter(f, fieldnames=COMPOSITE_KEYS)
		writer.writeheader()
		writer.writerows(prepared_rows)

	step3_time = time.time() - step3_start
	print(f"Wrote {len(prepared_rows)} rows to: {output_path} (took {step3_time:.2f}s)")
	
	total_time = time.time() - total_start
	print(f"\nWorkflow completed! Total execution time: {total_time:.2f}s")


if __name__ == "__main__":
	# Quick self-test path per repo guidance: keep tests in main()
	main()


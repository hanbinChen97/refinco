from __future__ import annotations
"""
Workflow runner: 
- Fetch wealth manager companies from SWF Institute, 
- enhance via Perplexity, and export to Excel.

Workflow:
1) Request the target listing pages and extract (companies + countries) using Azure OpenAI.
2) Fetch phone numbers from SWF profile pages for missing phone information.
3) For the first N companies, call Perplexity to enrich (contact + management) fields.
4) Scrape contact pages to enhance missing email/phone information.
5) Write output directly to Excel format.
"""
import datetime as dt
import os
import time
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from crawl4ai import AsyncWebCrawler
except ImportError:
    AsyncWebCrawler = None

try:
    import requests
    from bs4 import BeautifulSoup
    from urllib.parse import urljoin
except ImportError:
    requests = None
    BeautifulSoup = None
    urljoin = None

# Local utilities
from utils.get_company_list_from_swfinstitute import (
    get_company_list_from_swfinstitute,
)
from utils.enhance_info_with_perplexity import (
    enhance_company_info_with_perplexity,
    COMPOSITE_KEYS,
)
from utils.openai_llm import generate_text_with_web_search

BASE_SWF = "https://dev.swfinstitute.org"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _default_output_path() -> str:
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    return os.path.join(out_dir, f"wealth_managers_europe_{ts}.xlsx")


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


def fetch_profile_attributes(url: str) -> dict:
    """Fetch profile attributes including phone number from company profile page."""
    if requests is None or BeautifulSoup is None:
        print("Warning: requests and BeautifulSoup are required for profile scraping")
        return {}
    
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        table_container = soup.select_one(
            "#swfiProfileSingle > section:nth-child(2) > div > div:nth-child(2) > div.table-responsive"
        )
        if not table_container:
            return {}

        table = table_container.find("table")
        if not table:
            return {}

        result = {}
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).replace(":", "")
                value = cells[1].get_text(strip=True)
                if key and value:
                    result[key] = value

        return result
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return {}


def enhance_companies_with_swf_phone(companies: List[Dict[str, Optional[str]]], enable: bool) -> List[Dict[str, Optional[str]]]:
    """Enhance company info by fetching phone numbers from SWF profile pages."""
    if not enable or not companies:
        return companies
    
    print("Step 2: Enhancing with SWF profile phone numbers...")
    step2_start = time.time()
    
    enhanced_count = 0
    
    for i, company in enumerate(companies):
        # Check if we need to fetch phone number
        company_phone = company.get('company_phone')
        swf_url = company.get('swf_url')
        
        # Skip if phone already exists or no SWF URL
        if company_phone or not swf_url:
            continue
        
        company_name = company.get('company_name', 'Unknown')
        print(f"({i+1}/{len(companies)}) Fetching phone for {company_name}...")
        
        # Fetch profile attributes
        profile_attrs = fetch_profile_attributes(swf_url)
        if 'Phone' in profile_attrs:
            company['company_phone'] = profile_attrs['Phone']
            print(f"  Found phone: {profile_attrs['Phone']}")
            enhanced_count += 1
        else:
            print(f"  No phone found")
        
        # Add a small delay to be respectful
        time.sleep(1)
    
    step2_time = time.time() - step2_start
    print(f"Enhanced {enhanced_count} companies with SWF phone numbers. (took {step2_time:.2f}s)")
    return companies


def enhance_companies_with_perplexity(companies: List[Dict[str, Optional[str]]], enable: bool) -> List[Dict[str, Optional[str]]]:
    """Enhance company info with Perplexity if enabled and API key is set."""
    if not enable or not companies:
        return companies
    print("Step 3: Enhancing with Perplexity...")
    step3_start = time.time()
    api_set = bool(os.getenv("PERPLEXITY_API_KEY"))
    if not api_set:
        print("Warning: PERPLEXITY_API_KEY is not set. Enhancement may yield empty fields.")
    try:
        companies = enhance_company_info_with_perplexity(companies)
        step3_time = time.time() - step3_start
        print(f"Enhancement completed. (took {step3_time:.2f}s)")
    except Exception as e:
        step3_time = time.time() - step3_start
        print(f"Enhancement error: {e}. Proceeding with base fields only. (took {step3_time:.2f}s)")
    return companies


async def scrape_contact_page(url: str) -> Optional[str]:
    """Scrape the content from a contact page URL using AsyncWebCrawler."""
    if AsyncWebCrawler is None:
        logging.warning("crawl4ai not available, skipping page scraping")
        return None
    
    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
            if hasattr(result, 'markdown') and result.markdown:
                return result.markdown[:5000]  # Limit text length
            elif hasattr(result, 'cleaned_html') and result.cleaned_html:
                return result.cleaned_html[:5000]
            return None
    except Exception as e:
        logging.error(f"Error scraping {url}: {str(e)}")
        return None


def extract_contact_info_with_llm(webpage_content: str) -> tuple[Optional[str], Optional[str]]:
    """Use OpenAI LLM to extract email and phone from webpage content."""
    prompt = f"""
Please extract the main company contact information from this webpage content:

{webpage_content}

Please return ONLY a JSON object with the following format:
{{
    "company_email": "email@example.com or null if not found",
    "company_phone": "+1234567890 or null if not found"
}}

Rules:
- Look for general company contact email (like info@, contact@, hello@) rather than personal emails
- Look for main company phone number 
- If multiple emails/phones exist, choose the most general/official one
- Return null if no reliable contact information is found
- Do not include any explanation, just return the JSON object
"""
    
    try:
        result = generate_text_with_web_search(prompt)
        response_text = result.get("text", "")
        
        # Try to parse JSON from response
        # Find JSON in response (sometimes LLM adds extra text)
        start_idx = response_text.find('{')
        end_idx = response_text.rfind('}') + 1
        
        if start_idx != -1 and end_idx > start_idx:
            json_str = response_text[start_idx:end_idx]
            contact_info = json.loads(json_str)
            
            # Clean up null strings
            email = contact_info.get("company_email")
            phone = contact_info.get("company_phone")
            
            if email == "null" or email == "None":
                email = None
            if phone == "null" or phone == "None":
                phone = None
                
            return email, phone
        else:
            logging.warning("Could not parse JSON from LLM response")
            return None, None
            
    except Exception as e:
        logging.error(f"Error extracting contact info with LLM: {str(e)}")
        return None, None


async def enhance_companies_with_contact_pages(companies: List[Dict[str, Optional[str]]]) -> List[Dict[str, Optional[str]]]:
    """Enhance companies by scraping their contact pages for missing email/phone info."""
    if not companies:
        return companies
    
    print("Step 4: Enhancing with contact page scraping...")
    step4_start = time.time()
    
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    
    enhanced_count = 0
    
    for i, company in enumerate(companies):
        # Check if we have a contact page URL and missing email/phone
        contact_page = company.get('company_contact_page')
        company_email = company.get('company_email')
        company_phone = company.get('company_phone')
        
        # Skip if no contact page URL
        if not contact_page:
            continue
        
        # Skip if both email and phone are already populated
        if company_email and company_phone:
            continue
        
        company_name = company.get('company_name', 'Unknown')
        logger.info(f"Processing {company_name} - {contact_page}")
        
        # Scrape the contact page
        webpage_content = await scrape_contact_page(contact_page)
        
        if webpage_content:
            # Extract contact info using LLM
            extracted_email, extracted_phone = extract_contact_info_with_llm(webpage_content)
            
            # Update the company data if we found new information
            updated = False
            
            if extracted_email and not company_email:
                company['company_email'] = extracted_email
                logger.info(f"Added email for {company_name}: {extracted_email}")
                updated = True
            
            if extracted_phone and not company_phone:
                company['company_phone'] = extracted_phone
                logger.info(f"Added phone for {company_name}: {extracted_phone}")
                updated = True
            
            if updated:
                enhanced_count += 1
        
        # Add a small delay to be respectful to websites
        await asyncio.sleep(1)
    
    step4_time = time.time() - step4_start
    print(f"Enhanced {enhanced_count} companies with contact page data. (took {step4_time:.2f}s)")
    return companies


def write_companies_to_excel(companies: List[Dict[str, Optional[str]]], output_path: str) -> None:
    """Write companies directly to Excel with unified columns."""
    print("Step 5: Writing Excel...")
    step5_start = time.time()
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    if pd is None:
        raise ImportError("pandas is required for Excel export. Install with: pip install pandas openpyxl")

    # Prepare data with proper column order
    prepared_rows: List[Dict[str, str]] = []
    for row in companies:
        r: Dict[str, str] = {}
        for key in COMPOSITE_KEYS:
            val = row.get(key) if isinstance(row, dict) else None
            r[key] = "" if val is None else str(val)
        prepared_rows.append(r)

    # Create DataFrame and write to Excel
    df = pd.DataFrame(prepared_rows)
    
    # Ensure all columns exist in the desired order
    for col in COMPOSITE_KEYS:
        if col not in df.columns:
            df[col] = pd.NA
    
    # Reorder columns to match COMPOSITE_KEYS
    df = df[COMPOSITE_KEYS]
    
    # Write to Excel
    xlsx_path = Path(output_path)
    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)

    step5_time = time.time() - step5_start
    print(f"Wrote {len(prepared_rows)} rows to: {output_path} (took {step5_time:.2f}s)")


def collect_companies_from_base_urls(base_urls: List[str], pages: int) -> List[Dict[str, Optional[str]]]:
    """Collect companies from multiple base listing URLs (per-region), deduplicate and return list."""
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
    return all_companies


async def main():
    """Programmatic runner without CLI.

    Defaults:
    - base_urls: SWF Institute Europe and Asia wealth manager listings
    - pages: 3
    - limit: 0 (no limit - output all companies)
    - enhance_swf_phone: True (use SWF profile pages for phone numbers)
    - enhance_perplexity: True (use Perplexity if available)
    - enhance_contact: True (use contact page scraping if available)
    - output: data/wealth_managers_combined_<timestamp>.xlsx
    """
    print("Starting wealth manager data collection workflow...")
    total_start = time.time()

    base_urls = [
        "https://dev.swfinstitute.org/profiles/wealth-manager/europe",
        "https://dev.swfinstitute.org/profiles/wealth-manager/asia"
    ]
    pages = 3
    limit = 0  # 0 means no limit - output all companies
    enhance_swf_phone = True  # Enable SWF profile phone enhancement
    enhance_perplexity = True  # Enable Perplexity enhancement
    enhance_contact = True  # Enable contact page scraping

    # Step 1: Collect companies
    all_companies = collect_companies_from_base_urls(base_urls, pages)

    # Step 2: Enhance with SWF profile phone numbers
    limit = max(0, limit)
    selected = all_companies[:limit] if limit else all_companies
    print(f"Selected {len(selected)} companies for processing.")
    selected = enhance_companies_with_swf_phone(selected, enhance_swf_phone)

    # Step 3: Enhance with Perplexity
    selected = enhance_companies_with_perplexity(selected, enhance_perplexity)

    # Step 4: Enhance with contact page scraping
    if enhance_contact:
        selected = await enhance_companies_with_contact_pages(selected)

    # Step 5: Write directly to Excel
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(out_dir, exist_ok=True)
    output_path = os.path.join(out_dir, f"wealth_managers_combined_{ts}.xlsx")
    write_companies_to_excel(selected, output_path)

    total_time = time.time() - total_start
    print(f"\nWorkflow completed! Total execution time: {total_time:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
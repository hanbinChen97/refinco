import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict
import time

BASE = "https://dev.swfinstitute.org"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

def parse_company_urls(container) -> List[Dict[str, str]]:
    """
    Extract company names and URLs from swfinstitute.org listing page
    """
    if container is None:
        return []

    if isinstance(container, str):
        _soup = BeautifulSoup(container, "html.parser")
        container = _soup.find("div", class_="list-group list-group-wrap") or _soup

    items: List[Dict[str, str]] = []
    seen = set()
    for a in container.find_all("a", href=True):
        raw_href = a.get("href", "")
        if "/profile/" not in raw_href:
            continue
        href = urljoin(BASE, raw_href)

        title_el = a.select_one("strong.list-group-item-title") or a.find("strong")
        name = (title_el.get_text(strip=True) if title_el else a.get_text(strip=True))
        name = name.strip()
        if not name:
            continue

        if href and href not in seen:
            seen.add(href)
            items.append({
                "company_name": name,
                "url": href,
            })
    return items

def fetch_companies_from_region(region_url, max_pages=3):
    """Fetch ALL companies from a specific region (europe or asia) across all pages"""
    all_companies = []
    
    for page in range(1, max_pages + 1):
        # Add page parameter to URL
        page_url = f"{region_url}?page={page}"
        print(f"Fetching page {page}: {page_url}")
        
        try:
            response = requests.get(page_url, headers=HEADERS)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")
            list_container = soup.find("div", class_="list-group list-group-wrap")
            
            if not list_container:
                print(f"No more content found on page {page}")
                break
                
            page_companies = parse_company_urls(list_container)
            if not page_companies:
                print(f"No companies found on page {page}")
                # Don't break here, continue to next page in case there are gaps
                continue
                
            print(f"Found {len(page_companies)} companies on page {page}")
            all_companies.extend(page_companies)
            
        except Exception as e:
            print(f"Error fetching page {page}: {e}")
            continue
        
        time.sleep(1)  # Be respectful to the server
    
    print(f"Total companies found in region: {len(all_companies)}")
    return all_companies

def fetch_profile_attributes(url: str) -> dict:
    """
    Fetch profile attributes including phone number from company profile page
    """
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

def main():
    # Read existing Excel file
    print("Reading existing Excel file...")
    df = pd.read_excel('output/wealth_managers_enhanced.xlsx')
    
    print(f"Shape: {df.shape}")
    print(f"Columns: {df.columns.tolist()}")
    
    # Fetch all companies from both regions
    print("\nFetching companies from Europe...")
    europe_companies = fetch_companies_from_region("https://dev.swfinstitute.org/profiles/wealth-manager/europe")
    
    print(f"Found {len(europe_companies)} companies in Europe")
    
    print("\nFetching companies from Asia...")
    asia_companies = fetch_companies_from_region("https://dev.swfinstitute.org/profiles/wealth-manager/asia")
    
    print(f"Found {len(asia_companies)} companies in Asia")
    
    # Combine all companies
    all_swf_companies = europe_companies + asia_companies
    print(f"Total companies from SWF: {len(all_swf_companies)}")
    
    # Create a mapping from company name to URL
    name_to_url = {}
    for comp in all_swf_companies:
        name_to_url[comp['company_name']] = comp['url']
    
    # Add URL column by matching company names
    print("\nMatching companies and adding URLs...")
    df['url'] = df.apply(lambda row: name_to_url.get(row['company_name'], ''), axis=1)
    
    # Check how many matches we got
    matches = (df['url'] != '').sum()
    print(f"Successfully matched {matches} out of {len(df)} companies")
    
    # Check company_phone field and supplement missing ones
    if 'company_phone' in df.columns:
        missing_phone_mask = df['company_phone'].isna() | (df['company_phone'] == '') | (df['company_phone'] == 'N/A')
        missing_phone_count = missing_phone_mask.sum()
        print(f"\nFound {missing_phone_count} companies with missing phone numbers")
        
        if missing_phone_count > 0:
            print("Fetching phone numbers from profile pages...")
            count = 0
            for idx, row in df[missing_phone_mask & (df['url'] != '')].iterrows():
                count += 1
                print(f"({count}/{missing_phone_count}) Fetching phone for {row['company_name']}...")
                profile_attrs = fetch_profile_attributes(row['url'])
                if 'Phone' in profile_attrs:
                    df.at[idx, 'company_phone'] = profile_attrs['Phone']
                    print(f"  Found phone: {profile_attrs['Phone']}")
                else:
                    print(f"  No phone found")
                
                # Add a small delay to be respectful
                time.sleep(1)
    
    # Save the enhanced file
    output_path = 'output/wealth_managers_enhanced_with_urls.xlsx'
    df.to_excel(output_path, index=False)
    print(f"\nSaved enhanced file to {output_path}")
    
    # Show summary
    print(f"\nSummary:")
    print(f"Total companies: {len(df)}")
    print(f"Companies with URLs: {(df['url'] != '').sum()}")
    if 'company_phone' in df.columns:
        phone_available = (~(df['company_phone'].isna() | (df['company_phone'] == '') | (df['company_phone'] == 'N/A'))).sum()
        print(f"Companies with phone numbers: {phone_available}")

if __name__ == "__main__":
    main()
"""Utility functions for scraping company data."""

from __future__ import annotations

import time
import re
from typing import Optional

import requests
import pandas as pd
from bs4 import BeautifulSoup


BASE_URL = "https://disfold.com/japan/companies/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}


def _normalize_headers(headers: list[str]) -> list[str]:
    return [re.sub(r"\s+", "_", h.strip().lower()) for h in headers]


def get_target_companies(target_rows: int = 50) -> pd.DataFrame:
    """Scrape Disfold Japan companies list until ``target_rows`` rows collected.

    Only one public parameter is accepted: ``target_rows``.
    Internal defaults (can be adjusted in code if needed):
    - max_pages = 20
    - sleep = 1.0 seconds between requests

    Returns
    -------
    DataFrame
        Columns: [Company, Sector, Industry]
    """

    cols = ["Company", "Sector", "Industry"]
    companies_df = pd.DataFrame(columns=cols)

    if target_rows <= 0:
        return companies_df

    max_pages = 20
    sleep = 1.0
    sess = requests.Session()

    for page in range(1, max_pages + 1):
        if len(companies_df) >= target_rows:
            break

        url = BASE_URL if page == 1 else f"{BASE_URL}?page={page}"
        try:
            resp = sess.get(url, headers=HEADERS, timeout=30)
        except Exception:
            break
        if resp.status_code != 200:
            break

        soup = BeautifulSoup(resp.text, "lxml") if BeautifulSoup else BeautifulSoup(resp.text, "html.parser")

        # Identify the company table heuristically (must contain a header with 'company')
        table = None
        for tbl in soup.select("table"):
            header_cells = [th.get_text(strip=True).lower() for th in tbl.select("thead th")] or [
                th.get_text(strip=True).lower() for th in tbl.select("tr th")
            ]
            if any("company" in h for h in header_cells):
                table = tbl
                break
        if table is None:
            time.sleep(sleep)
            continue

        headers = [th.get_text(strip=True) for th in table.select("thead th")]
        if not headers:
            first_tr = table.select_one("tr")
            if first_tr:
                headers = [c.get_text(strip=True) for c in first_tr.find_all(["th", "td"])]
        norm_headers = _normalize_headers(headers)

        new_rows = []
        body_rows = table.select("tbody tr") or table.select("tr")[1:]
        for tr in body_rows:
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if not cells or all(not v for v in cells):
                continue
            if len(cells) < len(norm_headers):
                cells += [""] * (len(norm_headers) - len(cells))
            elif len(cells) > len(norm_headers):
                cells = cells[: len(norm_headers)]
            row = dict(zip(norm_headers, cells))
            # Flexible mapping
            company_name = row.get("company") or row.get("company_name") or row.get("name")
            sector = row.get("sector")
            industry = row.get("industry")
            if not company_name:
                continue
            new_rows.append({
                "Company": company_name,
                "Sector": sector,
                "Industry": industry,
            })

        if not new_rows:
            time.sleep(sleep)
            continue

        df_page = pd.DataFrame(new_rows)
        before = len(companies_df)
        companies_df = pd.concat([companies_df, df_page], ignore_index=True)
        # Deduplicate by company name (case-insensitive)
        companies_df["_norm"] = companies_df["Company"].str.strip().str.lower()
        companies_df = companies_df.drop_duplicates("_norm").drop(columns="_norm")

        time.sleep(sleep)

    if len(companies_df) > target_rows:
        companies_df = companies_df.head(target_rows).reset_index(drop=True)

    # Ensure required columns present
    for c in cols:
        if c not in companies_df.columns:
            companies_df[c] = None
    return companies_df[cols]


__all__ = ["get_target_companies"]

if __name__ == "__main__":
    # Example usage
    df = get_target_companies(target_rows=50)
    print(df.head())
    print(f"Total companies found: {len(df)}")
    print("Columns:", df.columns.tolist())
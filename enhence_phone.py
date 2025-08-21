'''
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from typing import List, Dict

url = "https://dev.swfinstitute.org/profiles/wealth-manager/europe"

# Define headers to increase request success rate
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# request url
response = requests.get(url, headers=HEADERS)
soup = BeautifulSoup(response.text, "html.parser")

# 处理 HTML 内容
list_container = soup.find("div", class_="list-group list-group-wrap")
print(list_container)

BASE = "https://dev.swfinstitute.org"


def parse_company_urls(container) -> List[Dict[str, str]]:
    """
    container: bs4.Tag | str | None
    Returns: list of dicts, each with keys: company_name, url
    Logic:
    - Only keep anchors linking to '/profile/...'
    - Company name is taken from <strong class="list-group-item-title"> if present, else fallback to anchor text
    """
    if container is None:
        return []

    # 如果传入的是 HTML 字符串，先解析
    if isinstance(container, str):
        _soup = BeautifulSoup(container, "html.parser")
        container = _soup.find("div", class_="list-group list-group-wrap") or _soup

    items: List[Dict[str, str]] = []
    seen = set()
    for a in container.find_all("a", href=True):
        raw_href = a.get("href", "")
        # 只保留 /profile/ 详情页链接
        if "/profile/" not in raw_href:
            continue
        href = urljoin(BASE, raw_href)

        # 优先从 strong.list-group-item-title 取公司名
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


companies_list = parse_company_urls(list_container)
print(f"Parsed {len(companies_list)} companies")

# 预览前 5 条
for item in companies_list[:5]:
    print(item)

# 最终输出
# companies_list

现在再给 output/wealth_managers_enhanced.xlsx 添加一个 column：url，也就是每个公司在 swfinstitute.org 的详情页链接。
上面只有 europa，还有 asia 的，请你同时适配。
		"https://dev.swfinstitute.org/profiles/wealth-manager/europe",
		"https://dev.swfinstitute.org/profiles/wealth-manager/asia"
    

def fetch_profile_attributes(url: str) -> dict:
    """
    Fetch a profile page and extract attributes (e.g., Phone, Country, City) from the table.
    Returns a dict with available keys.
    """
    # Define headers to increase request success rate
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
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


# 简单自测
if __name__ == "__main__":
    test_url = "https://dev.swfinstitute.org/profile/5dabfa3c5295eb340fa1028f"
    attrs = fetch_profile_attributes(test_url)
    print({k: attrs.get(k) for k in ("Phone", "Country", "City")})

查看表格的phone字段，如果缺失就用这个方法，request 然后添加。
'''
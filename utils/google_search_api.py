'''
封装 Google 搜索 API 请求
input: 查询字符串


'''
import os
import requests
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from pprint import pprint

load_dotenv()

API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
CX = os.getenv("GOOGLE_SEARCH_CX")

def google_search_titles(query: str, *, api_key: Optional[str] = None, cx: Optional[str] = None, n: int = 10) -> str:
    """执行 Google 自定义搜索并返回所有结果 title 拼接成的字符串。

    参数:
        query: 查询关键词。
        api_key: 覆盖默认环境变量中的 GOOGLE_SEARCH_API_KEY。
        cx: 覆盖默认环境变量中的 GOOGLE_SEARCH_CX。
        n: 期望返回的最大结果数量 (API 仍受配额/实际返回限制)。

    返回:
        以换行分隔的所有结果 title 字符串；若失败返回空字符串。
    """
    key = api_key or API_KEY
    cx_val = cx or CX
    if not key or not cx_val:
        return ""

    params = {
        "key": key,
        "cx": cx_val,
        "q": query,
        "num": min(max(n, 1), 10)  # Google Custom Search API 单次最多 10
    }

    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=15)
        res.raise_for_status()
        data: Dict[str, Any] = res.json()
    except Exception:
        return ""

    items: List[Dict[str, Any]] = data.get("items", [])
    titles = [it.get("title", "").strip() for it in items if it.get("title")]
    return "\n".join(titles)

def google_search(query: str, *, api_key: Optional[str] = None, cx: Optional[str] = None, n: int = 6, print_results: bool = False) -> List[Dict[str, Any]]:
    """执行 Google 自定义搜索并返回搜索结果。

    参数:
        query: 查询关键词。
        api_key: 覆盖默认环境变量中的 GOOGLE_SEARCH_API_KEY。
        cx: 覆盖默认环境变量中的 GOOGLE_SEARCH_CX。
        n: 期望返回的最大结果数量 (API 仍受配额/实际返回限制)。
        print_results: 是否打印搜索结果的详细信息。

    返回:
        包含搜索结果的字典列表，每个字典包含 title, link, snippet 等信息。
    """
    key = api_key or API_KEY
    cx_val = cx or CX
    if not key or not cx_val:
        if print_results:
            print("Error: Missing API key or search engine ID")
        return []

    params = {
        "key": key,
        "cx": cx_val,
        "q": query,
        "num": min(max(n, 1), 10),  # Google Custom Search API 单次最多 10
        #      -d gl=de -d hl=de -d safe=off -d filter=0
        "gl": "de",
        "hl": "de",
        "safe": "off",
        "filter": 0
    }

    try:
        res = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=15)
        res.raise_for_status()
        data: Dict[str, Any] = res.json()
    except Exception as e:
        if print_results:
            print(f"Error during search: {e}")
        return []

    items: List[Dict[str, Any]] = data.get("items", [])
    
    if print_results:
        print(f"\nGoogle Search Results for: '{query}'")
        print("=" * 60)
        print(f"Found {len(items)} results")
        print("-" * 60)
        
        for i, item in enumerate(items, 1):
            title = item.get("title", "No title")
            url = item.get("link", "No URL")
            snippet = item.get("snippet", "No description")
            formatted_url = item.get("formattedUrl", url)
            
            print(f"\nResult {i}:")
            print(f"Title: {title}")
            print(f"URL: {url}")
            print(f"Description: {snippet}")
            if formatted_url != url:
                print(f"Formatted URL: {formatted_url}")
            
            # 显示其他有用信息
            if item.get("pagemap"):
                pagemap = item.get("pagemap", {})
                if "metatags" in pagemap and pagemap["metatags"]:
                    meta = pagemap["metatags"][0]
                    if meta.get("og:description"):
                        print(f"Meta Description: {meta.get('og:description')}")
                    if meta.get("og:type"):
                        print(f"Page Type: {meta.get('og:type')}")
            
            print("-" * 60)
    
    return items

def google_search_formattedUrl(query: str, *, api_key: Optional[str] = None, cx: Optional[str] = None, n: int = 3) -> List[str]:
    """执行 Google 自定义搜索并返回所有结果 snippet 拼接成的字符串。

    参数:
        query: 查询关键词。
        api_key: 覆盖默认环境变量中的 GOOGLE_SEARCH_API_KEY。
        cx: 覆盖默认环境变量中的 GOOGLE_SEARCH_CX。
        n: 期望返回的最大结果数量 (API 仍受配额/实际返回限制)。

    返回:
        以换行分隔的所有结果 snippet 字符串；若失败返回空字符串。
    """
    items = google_search(query, api_key=api_key, cx=cx, n=n)
    formatted_urls = [it.get("formattedUrl", "").strip() for it in items if it.get("formattedUrl")]
    return formatted_urls

def google_search_manager(query: str, *, api_key: Optional[str] = None, cx: Optional[str] = None, n: int = 6) -> List[Dict[str, Any]]:
    """
    Search for management information (CEO, Geschäftsführer, founder, co-founder) for a company.
    
    参数:
        query: Company name or query string
        api_key: 覆盖默认环境变量中的 GOOGLE_SEARCH_API_KEY
        cx: 覆盖默认环境变量中的 GOOGLE_SEARCH_CX
        n: 期望返回的最大结果数量
        
    返回:
        List of search results containing management information
    """
    # Management-related keywords in multiple languages
    management_keywords = [
        "CEO", "Geschäftsführer", "founder", "co-founder", 
        "managing director", "executive", "president", 
        "Gründer", "Mitgründer", "Vorstand"
    ]
    
    # Create search queries for different management roles
    search_queries = [
        f"{query} CEO",
        f"{query} Geschäftsführer", 
        f"{query} founder",
        f"{query} co-founder",
        f"{query} managing director",
        f"{query} Gründer"
    ]
    
    all_results = []
    
    for search_query in search_queries:
        try:
            results = google_search(search_query, api_key=api_key, cx=cx, n=n)
            # Add search query info to each result for context
            for result in results:
                result["search_query"] = search_query
            all_results.extend(results)
        except Exception as e:
            print(f"Error searching for '{search_query}': {e}")
            continue
    
    # Remove duplicates based on URL
    seen_urls = set()
    unique_results = []
    for result in all_results:
        url = result.get("link", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)
    
    return unique_results[:n*2]  # Return more results since we're combining multiple searches


def extract_management_info_from_results(search_results: List[Dict[str, Any]], company_name: str) -> List[str]:
    """
    简单提取管理人员搜索结果的标题和摘要。
    
    参数:
        search_results: Results from google_search_manager
        company_name: Name of the company
        
    返回:
        List of formatted result strings
    """
    if not search_results:
        return []
    
    formatted_results = []
    for i, result in enumerate(search_results, 1):
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        query = result.get("search_query", "")
        
        if title or snippet:
            result_text = f"Result {i} ({query}):\n"
            if title:
                result_text += f"  Title: {title}\n"
            if snippet:
                result_text += f"  Snippet: {snippet}\n"
            formatted_results.append(result_text)
    
    return formatted_results

if __name__ == "__main__":
    # Test the google_search_manager function
    test_company = "Inpagest A.G."
    print(f"Using API Key: {bool(API_KEY)} and CX: {CX}")
    print(f"Testing management search for: {test_company}")
    print("-" * 50)
    
    # Test management search
    results = google_search_manager(test_company, n=3)
    print(f"Found {len(results)} results for management search")
    
    for i, result in enumerate(results[:5], 1):
        print(f"\nResult {i}:")
        print(f"  Query: {result.get('search_query', 'N/A')}")
        print(f"  Title: {result.get('title', 'N/A')}")
        print(f"  Snippet: {result.get('snippet', 'N/A')[:150]}...")
        print(f"  URL: {result.get('link', 'N/A')}")
    
    # Test extraction function
    print("\n" + "="*50)
    print("Management Info Extraction:")
    mgmt_info = extract_management_info_from_results(results, test_company)
    print(f"Company: {test_company}")
    print(f"Total Results: {len(results)}")
    print(f"Formatted Results: {len(mgmt_info)} items")
    
    # Show first 2 formatted results
    for i, formatted_result in enumerate(mgmt_info[:2], 1):
        print(f"\nFormatted Result {i}:")
        print(formatted_result)
"""
Script: company_query_compare.py

功能:
- 接受 company name, country name 作为输入。
- 单独查询1: 返回 {"company_email": str | None, "company_phone": str | None, "company_contact_page": str | None}
- 单独查询2: 返回 {"ceo": str | None, "ceo_email": str | None, "ceo_phone": str | None,
               "cofounder": str | None, "cofounder_email": str | None, "cofounder_phone": str | None}

- 复合查询: 返回 {"company_name": str, "country": str, "ceo": str | None,
             "company_email": str | None, "company_contact_page": str | None, "company_phone": str | None,
             "ceo_email": str | None, "ceo_phone": str | None,
             "cofounder": str | None, "cofounder_email": str | None, "cofounder_phone": str | None}
- 对比复合查询与合并后的单个查询结果, 输出不同的部分。

依赖:
- 需要已配置 Azure OpenAI 环境变量 (参见 llm.py)。
- 使用 Google Custom Search (google_search_api.py)。

"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from utils.google_search_api import google_search, google_search_manager
from utils.llm import chat_once, extract_contact_info as llm_extract_contact


# -------------------------
# 辅助: 构建搜索上下文
# -------------------------

def _build_contact_search_context(company: str, country: Optional[str], n: int = 6) -> str:
    term = f"{company} {country}".strip() if country else company
    query = (
        f"{term} (contact page OR 'contact us' OR contacts) (email OR e-mail) (phone OR telephone OR tel)"
    )

    items = google_search(query, n=n, print_results=False) or []
    
    parts: List[str] = [f"Search: {query}"]
    for i, it in enumerate(items[:n], 1):
        title = it.get("title", "")
        snippet = it.get("snippet", "")
        url = it.get("link", "")
        if title or snippet:
            parts.append(f"Result {i}: {title}\n{snippet}\nURL: {url}")
    return "\n\n".join(parts)


def _build_management_search_context(company: str, country: Optional[str], n: int = 6) -> str:
    term = f"{company} {country}".strip() if country else company
    items = google_search_manager(term, n=n) or []
    parts: List[str] = [f"Search (management): {term}"]
    for i, it in enumerate(items[: n * 2], 1):
        title = it.get("title", "")
        snippet = it.get("snippet", "")
        url = it.get("link", "")
        sq = it.get("search_query", "")
        if title or snippet:
            parts.append(f"Result {i} ({sq}): {title}\n{snippet}\nURL: {url}")
    return "\n\n".join(parts)


# -------------------------
# LLM 解析 JSON 的小助手
# -------------------------

def _llm_json(system_message: str, user_message: str, *, temperature: float = 0.0, max_tokens: int = 600) -> Dict:
    """调用 LLM 并解析为 JSON。失败则返回空 dict。"""
    try:
        resp = chat_once(system_message, user_message, temperature=temperature, max_tokens=max_tokens)
        # 有些模型会返回 ```json 包裹
        text = (resp or "").strip()
        if text.startswith("```"):
            # 去掉围栏
            text = text.strip("`\n ")
            if text.startswith("json"):
                text = text[4:].lstrip("\n")
        return json.loads(text)
    except Exception:
        return {}


# -------------------------
# 单个查询
# -------------------------

def _guess_contact_page_url(company: str, country: Optional[str], n: int = 6) -> Optional[str]:
    """根据搜索结果推测公司的官方 Contact 页面 URL。尽量排除聚合/第三方站点。"""
    term = f"{company} {country}".strip() if country else company
    query = (
        f"{term} (contact page OR 'contact us' OR contacts) (email OR e-mail) (phone OR telephone OR tel)"
    )
    items = google_search(query, n=n, print_results=False) or []

    block_domains = [
        "linkedin.com", "facebook.com", "twitter.com", "instagram.com", "youtube.com",
        "wikipedia.org", "crunchbase.com", "rocketreach.co", "zoominfo.com", "pitchbook.com",
        "glassdoor", "indeed", "map", "google.com/maps", "bloomberg.com", "reuters.com",
        "yelp.com", "trustpilot.com", "opencorporates.com",
    ]

    def is_blocked(url: str) -> bool:
        u = url.lower()
        return any(b in u for b in block_domains)

    # 优先选择 URL/title 中含有 contact 的结果
    for it in items:
        url = (it.get("link") or "").strip()
        title = (it.get("title") or "").lower()
        if not url or is_blocked(url):
            continue
        if "contact" in url.lower() or "contact" in title or "kontakt" in title:
            return url

    # 次选第一个未被屏蔽的官网候选
    for it in items:
        url = (it.get("link") or "").strip()
        if url and not is_blocked(url):
            return url
    return None


def query_contact(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
    """返回 {company_email, company_phone, company_contact_page}。优先使用 LLM 结构化; 若失败回退到正则提取。"""
    context = _build_contact_search_context(company, country)
    sys = (
        "You extract the official company contact email and phone (not individuals) for the specified company from the provided web search context.\n"
        "Return strict JSON with exactly these keys: company_email (string or null), company_phone (string or null)."
    )
    usr = f"Company: {company}\nCountry: {country or ''}\n\nSearch Context:\n{context}\n\nExtract now."
    data = _llm_json(sys, usr, temperature=0.0, max_tokens=250)

    # 兜底: 若解析不到, 返回空; 也可按需调用 llm_extract_contact 进行正则回退
    email = (data.get("company_email") if isinstance(data, dict) else None) or None
    phone = (data.get("company_phone") if isinstance(data, dict) else None) or None
    page_url = _guess_contact_page_url(company, country)
    if email or phone:
        return {"company_email": email, "company_phone": phone, "company_contact_page": page_url}

    # 回退到较宽松的提取
    fallback = llm_extract_contact(context)
    return {
        "company_email": fallback.get("email"),
        "company_phone": fallback.get("phone"),
        "company_contact_page": page_url,
    }


def query_management(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
    """返回管理层与其联系方式字段。键: ceo, ceo_email, ceo_phone, cofounder, cofounder_email, cofounder_phone"""
    context = _build_management_search_context(company, country)
    sys = (
        "You extract management information (CEO and Co-founder) and their public contact details for the specified company from the provided web search context.\n"
        "Return strict JSON with exactly these keys: \n"
        "ceo, ceo_email, ceo_phone, cofounder, cofounder_email, cofounder_phone. Use null when unknown."
    )
    usr = f"Company: {company}\nCountry: {country or ''}\n\nSearch Context:\n{context}\n\nExtract now."
    data = _llm_json(sys, usr, temperature=0.0, max_tokens=350)

    def _get(d: Dict, k: str) -> Optional[str]:
        v = d.get(k) if isinstance(d, dict) else None
        return v if isinstance(v, str) or v is None else None

    return {
        "ceo": _get(data, "ceo"),
        "ceo_email": _get(data, "ceo_email"),
        "ceo_phone": _get(data, "ceo_phone"),
        "cofounder": _get(data, "cofounder") or _get(data, "co_founder"),
        "cofounder_email": _get(data, "cofounder_email"),
        "cofounder_phone": _get(data, "cofounder_phone"),
    }


# -------------------------
# 复合查询
# -------------------------

def query_composite(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
    """返回包含公司/国家、管理和联系信息的统一结果。"""
    # 同时给出联系与管理上下文
    ctx_contact = _build_contact_search_context(company, country)
    ctx_mgmt = _build_management_search_context(company, country)
    context = f"CONTACT CONTEXT\n{ctx_contact}\n\nMANAGEMENT CONTEXT\n{ctx_mgmt}"

    sys = (
        "You extract a unified, single JSON object about the company's contact and management info from the provided contexts.\n"
        "Return strict JSON with exactly these keys: company_name, country, ceo, company_email, company_contact_page, company_phone, ceo_email, ceo_phone, cofounder, cofounder_email, cofounder_phone.\n"
        "Use null for unknown values; do not invent."
    )
    usr = f"Company: {company}\nCountry: {country or ''}\n\nContexts:\n{context}\n\nExtract now."
    data = _llm_json(sys, usr, temperature=0.0, max_tokens=400)

    def _get(d: Dict, k: str) -> Optional[str]:
        v = d.get(k) if isinstance(d, dict) else None
        return v if isinstance(v, str) or v is None else None

    result = {
        "company_name": _get(data, "company_name") or company,
        "country": _get(data, "country") or (country or ""),
        "ceo": _get(data, "ceo"),
        "company_email": _get(data, "company_email"),
        "company_contact_page": _get(data, "company_contact_page"),
        "company_phone": _get(data, "company_phone"),
        "ceo_email": _get(data, "ceo_email"),
        "ceo_phone": _get(data, "ceo_phone"),
        "cofounder": _get(data, "cofounder") or _get(data, "co_founder"),
        "cofounder_email": _get(data, "cofounder_email"),
        "cofounder_phone": _get(data, "cofounder_phone"),
    }

    # 补充 company_contact_page，若 LLM 未提供
    if not result.get("company_contact_page"):
        result["company_contact_page"] = _guess_contact_page_url(company, country)

    return result


# -------------------------
# 对比逻辑
# -------------------------

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


def query_single_then_merge(company: str, country: Optional[str]) -> Dict[str, Optional[str]]:
    """
    执行两个单独查询(公司联系信息、管理层信息)并合并为统一结果。

    返回的键集与复合查询保持一致:
    {company_name, country, ceo, company_email, company_phone, ceo_email, ceo_phone,
     cofounder, cofounder_email, cofounder_phone}
    """
    contact = query_contact(company, country)
    mgmt = query_management(company, country)
    return _merge_single_results(company, country, contact, mgmt)


def diff_dicts(a: Dict[str, Optional[str]], b: Dict[str, Optional[str]]) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
    """返回键 -> (a_value, b_value) 的差异映射。仅在两边值不等时记录。"""
    out: Dict[str, Tuple[Optional[str], Optional[str]]] = {}
    keys = set(a.keys()) | set(b.keys())
    for k in sorted(keys):
        va = a.get(k)
        vb = b.get(k)
        if (va or vb) and (va != vb):
            out[k] = (va, vb)
    return out


# -------------------------
# CLI / Inline test
# -------------------------

def main():
    # 在此处设置测试参数（无需在终端输入）
    company: str = "Inpagest A.G."
    country: Optional[str] = "Germany"

    # 可选：若通过命令行传入则覆盖（company [country]），但不是必需
    import sys
    if len(sys.argv) > 1:
        company = sys.argv[1].strip()
        if len(sys.argv) > 2:
            c = sys.argv[2].strip()
            country = c if c else None

    # 运行“单个查询并合并” 与 “复合查询”
    merged_single = query_single_then_merge(company, country)
    composite = query_composite(company, country)
    differences = diff_dicts(composite, merged_single)

    # 输出
    print("=== 测试参数 ===")
    print(json.dumps({"company": company, "country": country}, ensure_ascii=False, indent=2))
    print("\n=== 单个查询结果(合并后) ===")
    print(json.dumps(merged_single, ensure_ascii=False, indent=2))
    print("\n=== 复合查询结果 ===")
    print(json.dumps(composite, ensure_ascii=False, indent=2))

    print("\n=== 差异(复合 vs 单个合并) ===")
    if not differences:
        print("无差异。")
        return
    for k, (v_comp, v_single) in differences.items():
        print(f"- {k}:")
        print(f"  复合: {v_comp}")
        print(f"  单个: {v_single}")


if __name__ == "__main__":
    main()

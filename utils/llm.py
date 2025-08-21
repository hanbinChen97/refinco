import os
import re
import json
from functools import lru_cache
from typing import List, Optional, cast, Dict, Union

from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
deployment = os.getenv("AZURE_OPENAI_MODEL") or "gpt-4.1"  # treat env model as deployment name
subscription_key = os.getenv("AZURE_OPENAI_API_KEY")
api_version = os.getenv("AZURE_OPENAI_API_VERSION")



if not all([endpoint, deployment, subscription_key, api_version]):
    missing = [
        name for name, val in [
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_MODEL", deployment),
            ("AZURE_OPENAI_KEY", subscription_key),
            ("AZURE_OPENAI_API_VERSION", api_version),
        ] if not val
    ]
    raise EnvironmentError(f"Missing required Azure OpenAI env vars: {', '.join(missing)}")


@lru_cache(maxsize=1)
def _get_client() -> AzureOpenAI:
    """Return a cached AzureOpenAI client instance."""
    # Cast after env validation so type checker knows they're str
    return AzureOpenAI(
        api_version=cast(str, api_version),
        azure_endpoint=cast(str, endpoint),
        api_key=cast(str, subscription_key),
    )


def chat_once(
    system_message: str,
    user_message: str,
    *,
    history: Optional[List[Dict[str, str]]] = None,
    temperature: float = 1.0,
    top_p: float = 1.0,
    max_tokens: int = 800,
    model: Optional[str] = None,
) -> str:
    """Send a single-turn (optionally continued) chat request.

    Args:
        system_message: Content for the system role.
        user_message: New user input.
        history: Optional prior messages (list of {role, content}). Should NOT include the new user message.
        temperature, top_p, max_tokens: Generation controls.
        model: Deployment name override (defaults to env / global deployment).
    Returns:
        Assistant reply text.
    """
    # We construct a list of dicts matching ChatCompletionMessageParam shape.
    msgs = [
        {"role": "system", "content": system_message},  # type: ignore[arg-type]
    ]
    if history:
        msgs.extend(history)  # type: ignore[arg-type]
    msgs.append({"role": "user", "content": user_message})  # type: ignore[arg-type]

    client = _get_client()
    response = client.chat.completions.create(
        messages=cast(List, msgs),  # cast for type checker
        max_completion_tokens=max_tokens,  # Azure SDK parameter
        temperature=temperature,
        top_p=top_p,
        model=model or deployment,
    )
    return response.choices[0].message.content  # type: ignore


def make_agent(system_message: str):
    """Create an agent function with a fixed system message.

    Returns a callable: (user_message: str, **gen_kwargs) -> str
    """

    def _agent(user_message: str, **gen_kwargs) -> str:
        return chat_once(system_message, user_message, **gen_kwargs)

    return _agent


# Example: predefined helpful assistant agent
helpful_agent = make_agent("You are a helpful assistant.")


def extract_contact_info(soup_or_html) -> Dict[str, Optional[str]]:
    """
    Extract contact information (email and phone) from HTML content using LLM.
    
    Args:
        soup_or_html: BeautifulSoup object or HTML string
        
    Returns:
        Dict with 'email' and 'phone' keys, values can be None if not found
    """
    # Convert BeautifulSoup object to text
    if hasattr(soup_or_html, 'get_text'):
        # It's a BeautifulSoup object
        text_content = soup_or_html.get_text(separator=' ', strip=True)
    elif isinstance(soup_or_html, str):
        # It's HTML string, extract text roughly
        # Remove HTML tags using regex for basic extraction
        text_content = re.sub(r'<[^>]+>', ' ', soup_or_html)
        text_content = ' '.join(text_content.split())  # normalize whitespace
    else:
        return {"email": None, "phone": None}
    
    # Limit text length to avoid token limits
    if len(text_content) > 4000:
        text_content = text_content[:4000] + "..."
    
    system_message = """You are a contact information extraction specialist. Extract email addresses and phone numbers from the provided text content.

Return your response as a JSON object with exactly these keys:
- "email": the primary email address found (string or null)
- "phone": the primary phone number found (string or null)

Rules:
- Return only the most relevant/primary contact information
- For phone numbers, include country codes if present
- Return null if no valid email or phone is found
- Ensure the response is valid JSON"""

    user_message = f"Extract contact information from this text:\n\n{text_content}"
    
    try:
        response = chat_once(
            system_message, 
            user_message, 
            temperature=0.0, 
            max_tokens=200
        )
        
        # Try to parse as JSON
        contact_info = json.loads(response.strip())
        
        # Ensure we have the expected keys
        result = {
            "email": contact_info.get("email"),
            "phone": contact_info.get("phone")
        }
        
        return result
        
    except (json.JSONDecodeError, Exception) as e:
        # Fallback: try to extract using regex if LLM fails
        return _extract_contact_fallback(text_content)


def _extract_contact_fallback(text: str) -> Dict[str, Optional[str]]:
    """Fallback contact extraction using regex patterns."""
    # Email regex pattern
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    emails = re.findall(email_pattern, text)
    
    # Phone regex patterns (various formats)
    phone_patterns = [
        r'\+?\d{1,4}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}',  # International
        r'\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b',  # US format
        r'\b\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b',  # (123) 456-7890
    ]
    
    phones = []
    for pattern in phone_patterns:
        phones.extend(re.findall(pattern, text))
    
    return {
        "email": emails[0] if emails else None,
        "phone": phones[0] if phones else None
    }


def extract_management_info(search_results: List[Dict], company_name: str) -> Dict[str, Union[str, int, None]]:
    """
    使用 LLM 从 Google 搜索结果中提取管理人员信息。
    
    Args:
        search_results: Google 搜索结果列表
        company_name: 公司名称
        
    Returns:
        Dict 包含提取的管理人员信息
    """
    if not search_results:
        return {"error": "No search results provided"}
    
    # 构建搜索结果的上下文
    context_parts = []
    for i, result in enumerate(search_results[:8], 1):  # 限制前8个结果
        title = result.get("title", "")
        snippet = result.get("snippet", "")
        search_query = result.get("search_query", "")
        
        if title or snippet:
            context_parts.append(f"Result {i} (Search: {search_query}):")
            if title:
                context_parts.append(f"Title: {title}")
            if snippet:
                context_parts.append(f"Content: {snippet}")
            context_parts.append("")  # 空行分隔
    
    search_context = "\n".join(context_parts)
    
    # 限制上下文长度
    if len(search_context) > 6000:
        search_context = search_context[:6000] + "..."
    
    system_message = """You are a management information extraction specialist. Analyze the Google search results and extract key management personnel information for the specified company.

Extract the following information and return as JSON:
{
  "ceo": "Name of CEO/Chief Executive Officer (or null)",
  "founder": "Name of founder(s) (or null)", 
  "co_founder": "Name of co-founder(s) (or null)",
  "managing_director": "Name of managing director/Geschäftsführer (or null)",
  "other_executives": "Names of other key executives (or null)"
}

Rules:
- Only extract information that is clearly stated in the search results
- Focus on the specific company mentioned
- If multiple people hold the same role, separate names with commas
- Return null for roles where no information is found
- Ensure the response is valid JSON
- Be precise and avoid speculation"""

    user_message = f"""Company: {company_name}

Please extract management information from these Google search results:

{search_context}

Extract the management team information and return as JSON."""
    
    try:
        response = chat_once(
            system_message,
            user_message,
            temperature=0.1,
            max_tokens=500
        )
        
        # 尝试解析 JSON
        management_info = json.loads(response.strip())
        
        # 确保有预期的键
        result = {
            "company_name": company_name,
            "ceo": management_info.get("ceo"),
            "founder": management_info.get("founder"),
            "co_founder": management_info.get("co_founder"),
            "managing_director": management_info.get("managing_director"),
            "other_executives": management_info.get("other_executives"),
            "extraction_source": "google_search",
            "total_search_results": len(search_results)
        }
        
        return result
        
    except (json.JSONDecodeError, Exception) as e:
        # 如果 JSON 解析失败，返回错误信息
        return {
            "company_name": company_name,
            "error": f"Failed to extract management info: {str(e)}",
            "raw_response": response if 'response' in locals() else None,
            "total_search_results": len(search_results)
        }


if __name__ == "__main__":
    # Demo usage (single turn)
    reply = helpful_agent("Give me 3 must-see sights in Paris and a one-line why each matters.")
    print(reply)

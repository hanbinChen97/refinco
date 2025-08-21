import os
import sys
import dotenv

# Ensure project root is on sys.path so local modules can be imported when running this file by path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

dotenv.load_dotenv()
import dotenv

dotenv.load_dotenv()

def main():
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        print("SKIP: OPENAI_API_KEY not set; set it in your environment/.env to run this test.")
        sys.exit(0)

    try:
        from utils.openai_llm import generate_text_with_web_search
    except Exception as e:
        print(f"FAIL: import error: {e}")
        sys.exit(1)

    prompt = "Search the web and summarize the latest AI model announcements this month."
    print(f"Running OpenAI web search test...\nModel: gpt-4o-mini\nPrompt: {prompt[:80]}...")
    try:
        result = generate_text_with_web_search(prompt, model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    except Exception as e:
        print(f"FAIL: request error: {e}")
        sys.exit(2)

    text = (result or {}).get("text", "")
    sources = (result or {}).get("sources", [])
    text_len = len(text)
    print(f"TEXT_LEN={text_len} SOURCES={len(sources)}")

    # Print text for visibility; by default show preview unless OPENAI_TEST_SHOW_FULL_TEXT=1
    show_full = os.getenv("OPENAI_TEST_SHOW_FULL_TEXT") == "1"
    if text:
        if show_full or text_len <= 800:
            print("TEXT:\n" + text)
        else:
            preview = text[:800]
            print("TEXT_PREVIEW:\n" + preview + ("..." if text_len > 800 else ""))
    if not sources:
        print("NOTE: Sources are empty. Your account/model may not have web_search enabled.\n"
              "- Try another model with browsing, e.g., gpt-4o-mini, o4-mini (if available).\n"
              "- If using a proxy, set OPENAI_BASE_URL appropriately.\n"
              "- Check your plan features.")
    else:
        for i, s in enumerate(sources[:5], 1):
            print(f"  {i}. {s.get('title') or ''}\n     {s.get('url')}")

if __name__ == "__main__":
    main()

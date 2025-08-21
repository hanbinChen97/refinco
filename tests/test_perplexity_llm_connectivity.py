import os
import sys
import dotenv

# Ensure project root is on sys.path so local modules can be imported when running this file by path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

dotenv.load_dotenv()

def main():
    key = os.getenv("PERPLEXITY_API_KEY")
    if not key:
        print("SKIP: PERPLEXITY_API_KEY not set; set it in your environment/.env to run this test.")
        sys.exit(0)

    try:
        from utils.perplexity_llm import perplexity_generate_text
    except Exception as e:
        print(f"FAIL: import error: {e}")
        sys.exit(1)

    prompt = "Search the web and summarize recent quantum computing developments."
    model = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
    print(f"Running Perplexity test...\nModel: {model}\nPrompt: {prompt[:80]}...")
    try:
        result = perplexity_generate_text(prompt, model=model)
    except Exception as e:
        print(f"FAIL: request error: {e}")
        sys.exit(2)

    text = (result or {}).get("text", "")
    sources = (result or {}).get("sources", [])
    text_len = len(text)
    print(f"TEXT_LEN={text_len} SOURCES={len(sources)}")

    # Print text for visibility; by default show preview unless PPX_TEST_SHOW_FULL_TEXT=1
    show_full = os.getenv("PPX_TEST_SHOW_FULL_TEXT") == "1"
    if text:
        if show_full or text_len <= 800:
            print("TEXT:\n" + text)
        else:
            preview = text[:800]
            print("TEXT_PREVIEW:\n" + preview + ("..." if text_len > 800 else ""))
    if not sources:
        print("NOTE: Sources are empty. Citations may not be exposed on your plan or this model.\n"
              "- Try a different model (e.g., sonar, sonar-pro).\n"
              "- Ensure PERPLEXITY_API_BASE is correct (default https://api.perplexity.ai).")
    else:
        for i, s in enumerate(sources[:5], 1):
            print(f"  {i}. {s.get('title') or ''}\n     {s.get('url')}")

if __name__ == "__main__":
    main()

# RefinCo

A Python project for finding and analyzing company contact information using various search engines and APIs.

## Setup

This project uses [uv](https://docs.astral.sh/uv/) for Python package management.

1. Install uv if you haven't already:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   uv sync
   ```

3. Set up environment variables by copying and configuring the `.env` file:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

## Project Structure

```
refinco/
├── .env                 # Environment variables (API keys)
├── utils/               # Utility modules
│   ├── openai_llm.py   # OpenAI web search integration
│   ├── perplexity_llm.py # Perplexity search integration
│   ├── google_search_api.py # Google Custom Search
│   ├── crawl.py        # Web crawling utilities
│   └── ...
├── data/               # Data files and outputs
├── tests/              # Test files
└── main.py            # Main application entry point
```

### Environment Variables

Create a `.env` file in the project root with the following variables:

- **Google Custom Search**
  - `GOOGLE_SEARCH_API_KEY`
  - `GOOGLE_SEARCH_CX`
- **OpenAI Web Search**
  - `OPENAI_API_KEY`
  - `OPENAI_BASE_URL` (optional)
- **Perplexity**
  - `PERPLEXITY_API_KEY`
  - `PERPLEXITY_API_BASE` (optional, default: https://api.perplexity.ai)

## Web Search Wrappers

Available modules:
- `openai_llm.py`
	- `generate_text_with_web_search(prompt, model='gpt-4o-mini') -> { text, sources }`
	- `openai_web_search(query, model='gpt-4o-mini') -> sources`
- `perplexity_llm.py`
	- `perplexity_generate_text(prompt, model='sonar-pro') -> { text, sources }`
	- `perplexity_search(query, model='sonar-pro') -> sources`
- `find_contact_info.py`
	- `find_contact_info_simple_google_search(company, country=None, n=5) -> sources`
	- `find_contact_info_simple_openai(company, country=None, n=5) -> sources`
	- `find_contact_info_simple_perplexity(company, country=None, n=5) -> sources`
	- `compare_search_engines(company, country=None, n=5) -> { google, openai, perplexity }`

Run a quick comparison by executing `find_contact_info.py` directly (requires valid API keys). It will print the top 5 sources from each engine for a sample company.
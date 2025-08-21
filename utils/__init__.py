"""
utils package initializer.

- Ensures .env is loaded from the workspace root when importing any utils module.
- Keeps this package importable when running modules with `python -m`.
"""
from __future__ import annotations

from dotenv import load_dotenv

# Load .env from the project root (you run Python from the root)
try:
    load_dotenv()
except Exception:
    # Non-fatal if dotenv is missing or .env not found
    pass

# Re-export common entry points for convenience
try:
    from .get_company_list_from_website import get_company_list_from_website  # noqa: F401
except Exception:
    # Optional, module may be unavailable during certain execution contexts
    pass

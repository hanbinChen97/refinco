"""
csv2excel
---------

Lightweight utility functions to convert a CSV file to an Excel (.xlsx)
with a specific column order. No CLI is provided by design; import and use
from Python code.

Requirements:
- pandas
- openpyxl

Example
-------
from utils.csv2excel import csv_to_excel, DEFAULT_COLUMN_ORDER

csv_path = "data/wealth_managers_europe_20250817_200727.csv"
excel_path = csv_to_excel(csv_path, column_order=DEFAULT_COLUMN_ORDER)
print(f"Wrote: {excel_path}")
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional, Sequence

import pandas as pd

# Default column order as requested in plan.md
DEFAULT_COLUMN_ORDER: List[str] = [
	"company_name",
	"country",
	"company_contact_page",
	"company_email",
	"company_phone",
	"ceo",
	"ceo_email",
	"ceo_phone",
	"cofounder",
	"cofounder_email",
	"cofounder_phone",
]

DEFAULT_SHEET_NAME = "Sheet1"


def _read_csv_with_fallbacks(
	csv_path: Path,
	encoding: Optional[str] = None,
	sep: str = ",",
) -> pd.DataFrame:
	"""Read CSV using pandas with sensible encoding fallbacks.

	Tries in order:
	- provided encoding if given
	- "utf-8"
	- "utf-8-sig"
	- "latin-1"
	"""
	encodings: Sequence[str] = (
		[encoding] if encoding else []
	) + ["utf-8", "utf-8-sig", "latin-1"]

	last_err: Optional[Exception] = None
	for enc in encodings:
		try:
			return pd.read_csv(csv_path, encoding=enc, sep=sep)
		except Exception as e:  # pragma: no cover - best-effort fallback
			last_err = e
			continue
	# If all attempts failed, raise the last error
	assert last_err is not None
	raise last_err


def _ensure_columns(df: pd.DataFrame, required: Iterable[str]) -> pd.DataFrame:
	"""Ensure all required columns exist in the DataFrame; if missing, add as empty.

	Returns a new DataFrame reference (same underlying) for chaining.
	"""
	for col in required:
		if col not in df.columns:
			df[col] = pd.NA
	return df


def _reorder_columns(
	df: pd.DataFrame,
	column_order: Sequence[str],
	keep_extra_columns: bool = False,
) -> pd.DataFrame:
	"""Reorder columns to match column_order.

	- If keep_extra_columns is False (default), drops columns not in column_order.
	- If True, appends any extra columns at the end in their existing order.
	"""
	# Start with the desired columns, filtering to those that actually exist now
	ordered = [c for c in column_order if c in df.columns]
	if keep_extra_columns:
		extras = [c for c in df.columns if c not in ordered]
		ordered.extend(extras)
	return df[ordered]


def _resolve_output_path(csv_path: Path, excel_path: Optional[Path]) -> Path:
	if excel_path is not None:
		return excel_path
	return csv_path.with_suffix(".xlsx")


def csv_to_excel(
	csv_path: str | Path,
	excel_path: Optional[str | Path] = None,
	*,
	column_order: Optional[Sequence[str]] = None,
	keep_extra_columns: bool = False,
	sheet_name: str = DEFAULT_SHEET_NAME,
	index: bool = False,
	encoding: Optional[str] = None,
	sep: str = ",",
) -> str:
	"""Convert a CSV file to an Excel (.xlsx) with a specified column order.

	Parameters
	----------
	csv_path: Path-like to the input CSV file.
	excel_path: Optional path to write the Excel file. If omitted, uses the CSV
		path with ".xlsx" suffix in the same directory.
	column_order: Desired column order. If None, uses DEFAULT_COLUMN_ORDER.
	keep_extra_columns: If True, keeps any columns not listed in column_order
		and appends them to the end. If False, drops them. Default False.
	sheet_name: Excel sheet name. Default "Sheet1".
	index: Whether to write the index column to Excel. Default False.
	encoding: Optional CSV text encoding. If None, will try fallbacks.
	sep: CSV field separator. Default comma.

	Returns
	-------
	The absolute path to the written .xlsx file as a string.
	"""
	csv_p = Path(csv_path)
	xlsx_p = _resolve_output_path(csv_p, Path(excel_path) if excel_path else None)

	df = _read_csv_with_fallbacks(csv_p, encoding=encoding, sep=sep)

	desired_order = list(column_order) if column_order else list(DEFAULT_COLUMN_ORDER)
	_ensure_columns(df, desired_order)
	df = _reorder_columns(df, desired_order, keep_extra_columns=keep_extra_columns)

	xlsx_p.parent.mkdir(parents=True, exist_ok=True)
	with pd.ExcelWriter(xlsx_p, engine="openpyxl") as writer:
		df.to_excel(writer, sheet_name=sheet_name, index=index)

	return str(xlsx_p.resolve())


def main() -> None:
	"""Convert the specified CSV file to Excel format."""
	csv_path = "data/wealth_managers_combined_20250818_003634.csv"
	excel_path = csv_to_excel(csv_path, column_order=DEFAULT_COLUMN_ORDER)
	print(f"Converted CSV to Excel: {excel_path}")


if __name__ == "__main__":
	main()


__all__ = [
	"DEFAULT_COLUMN_ORDER",
	"csv_to_excel",
]


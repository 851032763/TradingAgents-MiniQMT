"""Small, dependency-light helpers for rendering provider tables in reports."""

from __future__ import annotations

import pandas as pd


def clean_table_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with empty rows/columns removed and missing values normalized."""
    if df is None:
        return pd.DataFrame()
    cleaned = df.copy()
    cleaned = cleaned.replace([float("inf"), float("-inf")], pd.NA)
    cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")
    return cleaned.fillna("")


def table_to_markdown(
    df: pd.DataFrame,
    *,
    max_rows: int = 12,
    max_cols: int = 18,
) -> str:
    """Render a bounded DataFrame as compact markdown suitable for LLM context."""
    cleaned = clean_table_for_display(df)
    if cleaned.empty:
        return "（暂无数据）"
    bounded = cleaned.head(max_rows).iloc[:, :max_cols]
    try:
        return bounded.to_markdown(index=False, tablefmt="github")
    except (ImportError, ValueError):
        # Keep reports usable if optional ``tabulate`` is unavailable.
        headers = [str(column) for column in bounded.columns]
        rows = [[str(value) for value in row] for row in bounded.itertuples(index=False, name=None)]
        lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        lines.extend("| " + " | ".join(row) + " |" for row in rows)
        return "\n".join(lines)

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any


DEFAULT_TIMEOUT_SECONDS = 30.0
COMMON_HEADERS = {
    "User-Agent": "paleo-paper-watcher/0.1 (+https://github.com/actions)",
}


def cutoff_date_for(lookback_days: int) -> date:
    return datetime.now(UTC).date() - timedelta(days=lookback_days)


def parse_date(value: Any) -> date | None:
    if value is None:
        return None

    if isinstance(value, date) and not isinstance(value, datetime):
        return value

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None

        if len(text) == 4 and text.isdigit():
            return date(int(text), 1, 1)

        try:
            return date.fromisoformat(text)
        except ValueError:
            pass

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            return None

    return None


def parse_crossref_date_parts(value: Any) -> date | None:
    if not isinstance(value, dict):
        return None

    parts = value.get("date-parts")
    if not parts or not isinstance(parts, list):
        return None

    first = parts[0]
    if not isinstance(first, list) or not first:
        return None

    year = first[0]
    month = first[1] if len(first) > 1 else 1
    day = first[2] if len(first) > 2 else 1

    try:
        return date(int(year), int(month), int(day))
    except (TypeError, ValueError):
        return None


def normalize_doi(value: str | None) -> str | None:
    if not value:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    lowered = normalized.lower()
    prefixes = (
        "https://doi.org/",
        "http://doi.org/",
        "https://dx.doi.org/",
        "http://dx.doi.org/",
        "doi:",
    )
    for prefix in prefixes:
        if lowered.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break

    normalized = normalized.strip()
    return normalized or None


def filter_recent_papers(papers: list, lookback_days: int) -> list:
    cutoff = cutoff_date_for(lookback_days)
    filtered = []
    for paper in papers:
        if paper.published_date is None or paper.published_date >= cutoff:
            filtered.append(paper)
    return filtered


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None

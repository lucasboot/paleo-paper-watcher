from __future__ import annotations

import logging
from typing import Any

import httpx

from src.models import Paper
from src.sources.base import (
    COMMON_HEADERS,
    DEFAULT_TIMEOUT_SECONDS,
    cutoff_date_for,
    filter_recent_papers,
    normalize_doi,
    parse_date,
)

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.openalex.org/works"


def _extract_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None

    tokens: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for position in positions:
            tokens.append((position, word))

    if not tokens:
        return None

    tokens.sort(key=lambda item: item[0])
    return " ".join(word for _, word in tokens)


def _extract_pdf_url(locations: list[dict[str, Any]] | None) -> str | None:
    if not locations:
        return None

    for location in locations:
        pdf_url = location.get("pdf_url")
        if pdf_url:
            return pdf_url
    return None


def _to_paper(item: dict[str, Any]) -> Paper:
    openalex_id = item.get("id", "").rstrip("/").split("/")[-1]
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    doi = normalize_doi(item.get("doi"))

    return Paper(
        source="openalex",
        external_id=openalex_id or doi or item.get("id") or item.get("display_name", "unknown"),
        title=item.get("display_name") or "Untitled",
        authors=[
            authorship.get("author", {}).get("display_name")
            for authorship in item.get("authorships", [])
            if authorship.get("author", {}).get("display_name")
        ],
        published_date=parse_date(item.get("publication_date")),
        doi=doi,
        url=primary_location.get("landing_page_url") or item.get("id"),
        pdf_url=primary_location.get("pdf_url") or _extract_pdf_url(item.get("locations")),
        abstract=_extract_abstract(item.get("abstract_inverted_index")),
        venue=source.get("display_name"),
        raw=item,
    )


async def search(query: str, lookback_days: int, max_results: int) -> list[Paper]:
    params = {
        "search": query,
        "filter": f"from_publication_date:{cutoff_date_for(lookback_days).isoformat()}",
        "sort": "publication_date:desc",
        "per-page": max_results,
    }

    try:
        async with httpx.AsyncClient(
            headers=COMMON_HEADERS,
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            response = await client.get(BASE_URL, params=params)
            response.raise_for_status()
    except Exception as exc:
        LOGGER.warning("OpenAlex search failed for query=%r: %s", query, exc)
        return []

    results = response.json().get("results", [])
    papers = [_to_paper(item) for item in results]
    return filter_recent_papers(papers, lookback_days)

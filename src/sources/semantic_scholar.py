from __future__ import annotations

import logging
from typing import Any

import httpx

from src.models import Paper
from src.sources.base import (
    DEFAULT_TIMEOUT_SECONDS,
    SEMANTIC_SCHOLAR_POLICY,
    cutoff_date_for,
    fetch_json_with_policy,
    filter_recent_papers,
    normalize_doi,
    parse_date,
    semantic_scholar_headers,
)

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = ",".join(
    [
        "paperId",
        "title",
        "authors",
        "year",
        "publicationDate",
        "url",
        "abstract",
        "openAccessPdf",
        "externalIds",
        "venue",
    ]
)
def _to_paper(item: dict[str, Any]) -> Paper:
    external_ids = item.get("externalIds") or {}
    doi = normalize_doi(external_ids.get("DOI"))
    published_date = parse_date(item.get("publicationDate")) or parse_date(str(item.get("year") or ""))
    open_access_pdf = item.get("openAccessPdf") or {}

    return Paper(
        source="semantic_scholar",
        external_id=item.get("paperId") or doi or item.get("url") or item.get("title", "unknown"),
        title=item.get("title") or "Untitled",
        authors=[author.get("name") for author in item.get("authors", []) if author.get("name")],
        published_date=published_date,
        language=item.get("language"),
        doi=doi,
        url=item.get("url"),
        pdf_url=open_access_pdf.get("url"),
        abstract=item.get("abstract"),
        venue=item.get("venue"),
        raw=item,
    )


async def search(query: str, lookback_days: int, max_results: int) -> list[Paper]:
    cutoff_year = cutoff_date_for(lookback_days).year
    params = {
        "query": query,
        "fields": FIELDS,
        "sort": "publicationDate:desc",
        "year": f"{cutoff_year}-",
    }

    try:
        async with httpx.AsyncClient(headers=semantic_scholar_headers(), timeout=DEFAULT_TIMEOUT_SECONDS) as client:
            payload = await fetch_json_with_policy(
                client=client,
                policy=SEMANTIC_SCHOLAR_POLICY,
                url=BASE_URL,
                params=params,
            )
    except Exception as exc:
        LOGGER.warning("Semantic Scholar search failed for query=%r: %s", query, exc)
        return []

    items = payload.get("data", [])[:max_results]
    papers = [_to_paper(item) for item in items]
    return filter_recent_papers(papers, lookback_days)

from __future__ import annotations

import logging
from typing import Any

import httpx

from src.models import Paper
from src.sources.base import (
    CROSSREF_POLICY,
    DEFAULT_TIMEOUT_SECONDS,
    cutoff_date_for,
    crossref_headers,
    crossref_params,
    fetch_json_with_policy,
    filter_recent_papers,
    first_non_empty,
    normalize_doi,
    parse_crossref_date_parts,
)

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://api.crossref.org/works"


def _extract_authors(item: dict[str, Any]) -> list[str]:
    authors = []
    for author in item.get("author", []):
        given = (author.get("given") or "").strip()
        family = (author.get("family") or "").strip()
        name = " ".join(part for part in (given, family) if part).strip()
        if name:
            authors.append(name)
    return authors


def _extract_pdf_url(item: dict[str, Any]) -> str | None:
    for link in item.get("link", []):
        content_type = (link.get("content-type") or "").lower()
        intended = (link.get("intended-application") or "").lower()
        if "pdf" in content_type or intended == "text-mining":
            url = link.get("URL")
            if url:
                return url
    return None


def _extract_published_date(item: dict[str, Any]):
    return first_non_empty(
        parse_crossref_date_parts(item.get("published-print")),
        parse_crossref_date_parts(item.get("published-online")),
        parse_crossref_date_parts(item.get("issued")),
    )


def _to_paper(item: dict[str, Any]) -> Paper:
    doi = normalize_doi(item.get("DOI"))
    title = first_non_empty(*item.get("title", [])) or "Untitled"

    return Paper(
        source="crossref",
        external_id=doi or item.get("URL") or title,
        title=title,
        authors=_extract_authors(item),
        published_date=_extract_published_date(item),
        language=item.get("language"),
        doi=doi,
        url=item.get("URL"),
        pdf_url=_extract_pdf_url(item),
        abstract=item.get("abstract"),
        venue=first_non_empty(*item.get("container-title", [])),
        raw=item,
    )


async def search(query: str, lookback_days: int, max_results: int) -> list[Paper]:
    cutoff = cutoff_date_for(lookback_days).isoformat()
    params = {
        "query.bibliographic": query,
        "filter": f"from-pub-date:{cutoff}",
        "rows": max_results,
        "sort": "published",
        "order": "desc",
    }
    params.update(crossref_params())

    try:
        async with httpx.AsyncClient(
            headers=crossref_headers(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            payload = await fetch_json_with_policy(
                client=client,
                policy=CROSSREF_POLICY,
                url=BASE_URL,
                params=params,
            )
    except Exception as exc:
        LOGGER.warning("Crossref search failed for query=%r: %s", query, exc)
        return []

    items = payload.get("message", {}).get("items", [])
    papers = [_to_paper(item) for item in items]
    return filter_recent_papers(papers, lookback_days)

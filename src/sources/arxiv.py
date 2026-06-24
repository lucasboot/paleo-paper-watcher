from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from src.models import Paper
from src.sources.base import (
    ARXIV_POLICY,
    DEFAULT_TIMEOUT_SECONDS,
    common_headers,
    fetch_response_with_policy,
    filter_recent_papers,
    normalize_doi,
    parse_date,
)

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://export.arxiv.org/api/query"
ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


def _text(element: ET.Element | None, path: str) -> str | None:
    if element is None:
        return None
    child = element.find(path, ATOM_NS)
    if child is None or child.text is None:
        return None
    return child.text.strip()


def _extract_pdf_url(entry: ET.Element) -> str | None:
    for link in entry.findall("atom:link", ATOM_NS):
        title = (link.attrib.get("title") or "").lower()
        content_type = (link.attrib.get("type") or "").lower()
        href = link.attrib.get("href")
        if href and (title == "pdf" or content_type == "application/pdf"):
            return href
    return None


def _entry_to_raw(entry: ET.Element) -> dict[str, Any]:
    return {
        "id": _text(entry, "atom:id"),
        "title": _text(entry, "atom:title"),
        "published": _text(entry, "atom:published"),
        "updated": _text(entry, "atom:updated"),
        "summary": _text(entry, "atom:summary"),
        "authors": [_text(author, "atom:name") for author in entry.findall("atom:author", ATOM_NS)],
        "doi": _text(entry, "arxiv:doi"),
        "pdf_url": _extract_pdf_url(entry),
    }


def _to_paper(entry: ET.Element) -> Paper:
    raw = _entry_to_raw(entry)
    arxiv_id = (raw.get("id") or "").rstrip("/").split("/")[-1]
    doi = normalize_doi(raw.get("doi"))

    return Paper(
        source="arxiv",
        external_id=arxiv_id or doi or raw.get("title") or "unknown",
        title=raw.get("title") or "Untitled",
        authors=[author for author in raw.get("authors", []) if author],
        published_date=parse_date(raw.get("published")),
        language=None,
        doi=doi,
        url=raw.get("id"),
        pdf_url=raw.get("pdf_url"),
        abstract=raw.get("summary"),
        venue="arXiv",
        raw=raw,
    )


async def search(query: str, lookback_days: int, max_results: int) -> list[Paper]:
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    try:
        async with httpx.AsyncClient(
            headers=common_headers(),
            timeout=DEFAULT_TIMEOUT_SECONDS,
        ) as client:
            response = await fetch_response_with_policy(
                client=client,
                policy=ARXIV_POLICY,
                url=BASE_URL,
                params=params,
            )
    except Exception as exc:
        LOGGER.warning("arXiv search failed for query=%r: %s", query, exc)
        return []

    root = ET.fromstring(response.text)
    papers = [_to_paper(entry) for entry in root.findall("atom:entry", ATOM_NS)]
    return filter_recent_papers(papers, lookback_days)

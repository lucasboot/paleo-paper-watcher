"""Source integrations for fetching papers."""

from src.sources import arxiv, crossref, openalex, semantic_scholar

SOURCE_MODULES = {
    "openalex": openalex,
    "crossref": crossref,
    "semantic_scholar": semantic_scholar,
    "arxiv": arxiv,
}

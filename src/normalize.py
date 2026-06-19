import re
import unicodedata

from src.models import Paper


def normalize_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKD", title)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    collapsed = re.sub(r"[^a-z0-9]+", " ", ascii_only.lower())
    return re.sub(r"\s+", " ", collapsed).strip()


def dedupe_key(paper: Paper) -> str:
    if paper.doi:
        return f"doi:{paper.doi.strip().lower()}"

    if paper.external_id:
        return f"external_id:{paper.external_id.strip().lower()}"

    return f"title:{normalize_title(paper.title)}"

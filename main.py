import asyncio
import logging

from src.config import load_config
from src.models import Paper
from src.normalize import dedupe_key
from src.sources import SOURCE_MODULES

SOURCE_ORDER = ("openalex", "crossref", "semantic_scholar", "arxiv")
SOURCE_CONCURRENCY = {
    "openalex": 2,
    "crossref": 1,
    "semantic_scholar": 1,
    "arxiv": 1,
}
SOURCE_SEMAPHORES = {
    source_name: asyncio.Semaphore(limit)
    for source_name, limit in SOURCE_CONCURRENCY.items()
}


async def run_source(source_name: str, query: str, lookback_days: int, max_results: int) -> list[Paper]:
    try:
        async with SOURCE_SEMAPHORES[source_name]:
            return await SOURCE_MODULES[source_name].search(query, lookback_days, max_results)
    except Exception as exc:
        logging.warning("source=%s query=%r failed: %s", source_name, query, exc)
        return []


def dedupe_papers(papers: list[Paper]) -> list[Paper]:
    seen_keys: set[str] = set()
    unique_papers: list[Paper] = []

    for paper in papers:
        key = dedupe_key(paper)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_papers.append(paper)

    return unique_papers


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    config = load_config("config.yaml")

    tasks = []
    for query in config.queries:
        for source_name in SOURCE_ORDER:
            source_config = config.get_source_config(source_name)
            if not source_config.enabled:
                continue
            tasks.append(
                run_source(
                    source_name=source_name,
                    query=query,
                    lookback_days=source_config.lookback_days,
                    max_results=source_config.max_results,
                )
            )

    results = await asyncio.gather(*tasks)
    papers = dedupe_papers([paper for batch in results for paper in batch])
    papers.sort(
        key=lambda paper: (paper.published_date is not None, paper.published_date),
        reverse=True,
    )

    for paper in papers:
        published = paper.published_date.isoformat() if paper.published_date else "unknown-date"
        url = paper.url or "-"
        print(f"{paper.title} | {paper.source} | {published} | {url}")


if __name__ == "__main__":
    asyncio.run(main())

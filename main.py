import asyncio
import logging
import os

from src.config import load_config
from src.formatters import format_daily_messages
from src.models import Paper
from src.notify import load_dotenv, send_messages
from src.notify.telegram import get_chat_ids
from src.normalize import dedupe_key
from src.state import load_seen_keys, save_seen_keys
from src.sources import SOURCE_MODULES
from src.summarize import summarize_papers

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


def language_rank(language: str | None, priorities: list[str]) -> int:
    if not language:
        return len(priorities)

    normalized = language.strip().lower()
    for index, priority in enumerate(priorities):
        if normalized == priority.lower():
            return index
        if normalized.startswith(f"{priority.lower()}-"):
            return index

    return len(priorities)


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


def filter_new_papers(papers: list[Paper], seen_keys: set[str]) -> list[Paper]:
    return [paper for paper in papers if dedupe_key(paper) not in seen_keys]


def chunk_papers(papers: list[Paper], chunk_size: int) -> list[list[Paper]]:
    return [papers[start : start + chunk_size] for start in range(0, len(papers), chunk_size)]


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    load_dotenv(".env")
    config = load_config("config.yaml")
    seen_keys = load_seen_keys("data/seen.json")

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
                    max_results=config.max_results_per_source,
                )
            )

    results = await asyncio.gather(*tasks)
    papers = dedupe_papers([paper for batch in results for paper in batch])
    papers.sort(
        key=lambda paper: (
            language_rank(paper.language, config.languages_priority),
            -(paper.published_date.toordinal() if paper.published_date else -1),
            paper.title.lower(),
        ),
    )
    new_papers = filter_new_papers(papers, seen_keys)

    if not new_papers:
        print("Nenhuma novidade encontrada.")
        return

    new_papers = await summarize_papers(new_papers, config)

    paper_chunks = chunk_papers(new_papers, config.notification.max_items_per_message)
    plain_messages = format_daily_messages(
        new_papers,
        max_items_per_message=config.notification.max_items_per_message,
        html=False,
    )
    html_messages = format_daily_messages(
        new_papers,
        max_items_per_message=config.notification.max_items_per_message,
        html=True,
    )

    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or not get_chat_ids():
        print("Telegram nao foi configurado. Imprimindo mensagens no terminal.")
        for index, message in enumerate(plain_messages):
            if index > 0:
                print()
            print(message)
        return

    sent_message_count = await send_messages(html_messages)

    if sent_message_count == 0:
        return

    delivered_papers = [
        paper
        for chunk in paper_chunks[:sent_message_count]
        for paper in chunk
    ]
    seen_keys.update(dedupe_key(paper) for paper in delivered_papers)
    save_seen_keys("data/seen.json", seen_keys)


if __name__ == "__main__":
    asyncio.run(main())

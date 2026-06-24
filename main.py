import asyncio
import logging
import os
from collections import defaultdict

from src.config import load_config
from src.formatters import format_daily_messages
from src.models import Paper
from src.notify import load_dotenv, send_messages
from src.notify.telegram import get_chat_ids
from src.normalize import dedupe_key
from src.relevance import RelevanceDecision, evaluate_relevance, summarize_decision
from src.state import load_seen_keys, save_seen_keys
from src.sources import SOURCE_MODULES
from src.sources.base import log_missing_source_configuration

SOURCE_ORDER = ("openalex", "crossref", "semantic_scholar", "arxiv")
SOURCE_CONCURRENCY = {
    "openalex": 1,
    "crossref": 1,
    "semantic_scholar": 1,
    "arxiv": 1,
}
SOURCE_SEMAPHORES = {
    source_name: asyncio.Semaphore(limit)
    for source_name, limit in SOURCE_CONCURRENCY.items()
}
PaperMatch = tuple[str, Paper]


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


def dedupe_papers(paper_matches: list[PaperMatch]) -> tuple[list[Paper], dict[str, list[str]]]:
    seen_keys: set[str] = set()
    unique_papers: list[Paper] = []
    queries_by_paper: dict[str, list[str]] = defaultdict(list)

    for query, paper in paper_matches:
        key = dedupe_key(paper)
        if query not in queries_by_paper[key]:
            queries_by_paper[key].append(query)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_papers.append(paper)

    return unique_papers, dict(queries_by_paper)


def filter_new_papers(papers: list[Paper], seen_keys: set[str]) -> list[Paper]:
    return [paper for paper in papers if dedupe_key(paper) not in seen_keys]


def chunk_papers(papers: list[Paper], chunk_size: int) -> list[list[Paper]]:
    return [papers[start : start + chunk_size] for start in range(0, len(papers), chunk_size)]


def apply_relevance_filters(
    papers: list[Paper],
    enabled: bool,
    filters_config,
) -> tuple[list[Paper], list[tuple[Paper, RelevanceDecision]], dict[str, RelevanceDecision]]:
    if not enabled:
        return papers, [], {}

    approved: list[Paper] = []
    rejected: list[tuple[Paper, RelevanceDecision]] = []
    decisions_by_paper: dict[str, RelevanceDecision] = {}
    for paper in papers:
        decision = evaluate_relevance(paper, filters_config)
        decisions_by_paper[dedupe_key(paper)] = decision
        if decision.approved:
            approved.append(paper)
            continue
        rejected.append((paper, decision))

    return approved, rejected, decisions_by_paper


def log_filtered_papers(filtered_papers: list[tuple[Paper, RelevanceDecision]]) -> None:
    if not filtered_papers:
        return

    print(f"{len(filtered_papers)} artigo(s) filtrado(s) por relevancia:")
    for paper, decision in filtered_papers:
        positive_text = "; ".join(decision.positive_reasons) if decision.positive_reasons else "nenhum"
        negative_text = "; ".join(decision.negative_reasons) if decision.negative_reasons else "nenhum"
        print(
            f"FILTRADO: [{paper.source}] direct_score={decision.direct_score} "
            f"| methodological_score={decision.methodological_score} | categoria={decision.category} "
            f"| {paper.title} | positivos: {positive_text} | negativos: {negative_text}"
        )
    print()


def build_relevance_summaries(decisions_by_paper: dict[str, RelevanceDecision]) -> dict[str, str]:
    summaries: dict[str, str] = {}
    for paper_key, decision in decisions_by_paper.items():
        summaries[paper_key] = summarize_decision(decision)
    return summaries


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    load_dotenv(".env")
    log_missing_source_configuration()
    config = load_config("config.yaml")
    seen_keys = load_seen_keys("data/seen.json")

    tasks: list[asyncio.Future | asyncio.Task] = []
    task_queries: list[str] = []
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
            task_queries.append(query)

    results = await asyncio.gather(*tasks)
    paper_matches = [
        (query, paper)
        for query, batch in zip(task_queries, results)
        for paper in batch
    ]
    papers, queries_by_paper = dedupe_papers(paper_matches)
    papers.sort(
        key=lambda paper: (
            language_rank(paper.language, config.languages_priority),
            -(paper.published_date.toordinal() if paper.published_date else -1),
            paper.title.lower(),
        ),
    )
    papers, filtered_out_papers, decisions_by_paper = apply_relevance_filters(
        papers,
        enabled=config.filters.enabled,
        filters_config=config.filters,
    )
    log_filtered_papers(filtered_out_papers)
    relevance_by_paper = build_relevance_summaries(decisions_by_paper)

    new_papers = filter_new_papers(papers, seen_keys)

    if not new_papers:
        if filtered_out_papers:
            print("Nenhuma novidade relevante encontrada.")
        else:
            print("Nenhuma novidade encontrada.")
        return

    paper_chunks = chunk_papers(new_papers, config.notification.max_items_per_message)
    plain_messages = format_daily_messages(
        new_papers,
        max_items_per_message=config.notification.max_items_per_message,
        html=False,
        queries_by_paper=queries_by_paper,
        relevance_by_paper=relevance_by_paper,
    )
    html_messages = format_daily_messages(
        new_papers,
        max_items_per_message=config.notification.max_items_per_message,
        html=True,
        relevance_by_paper=relevance_by_paper,
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

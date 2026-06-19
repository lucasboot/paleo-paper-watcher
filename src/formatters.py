from __future__ import annotations

from datetime import date, datetime

from src.models import Paper


def format_paper(paper: Paper, index: int) -> str:
    published = paper.published_date.isoformat() if paper.published_date else "desconhecido"
    authors = ", ".join(paper.authors) if paper.authors else "nao informado"
    doi = paper.doi or "nao encontrado"
    pdf_status = "disponivel" if paper.pdf_url else "nao encontrado"
    link = paper.url or "nao encontrado"

    return (
        f"{index}. {paper.title}\n"
        f"Fonte: {paper.source}\n"
        f"Publicado: {published}\n"
        f"Autores: {authors}\n"
        f"DOI: {doi}\n"
        f"PDF: {pdf_status}\n"
        f"Link: {link}"
    )


def format_daily_messages(
    papers: list[Paper],
    max_items_per_message: int,
    run_date: date | None = None,
) -> list[str]:
    if not papers:
        return []

    effective_date = run_date or datetime.now().date()
    header = (
        f"Novidades em Paleopalinologia - {effective_date.strftime('%d/%m/%Y')}\n\n"
        f"Encontrei {len(papers)} possiveis novidades."
    )

    messages: list[str] = []
    for start in range(0, len(papers), max_items_per_message):
        chunk = papers[start : start + max_items_per_message]
        body = "\n\n".join(
            format_paper(paper, index)
            for index, paper in enumerate(chunk, start=start + 1)
        )
        messages.append(f"{header}\n\n{body}")

    return messages

from __future__ import annotations

from datetime import date, datetime

from src.models import Paper


def _escape_markdown(text: str) -> str:
    escaped = text
    for char in ("\\", "_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
        escaped = escaped.replace(char, f"\\{char}")
    return escaped


def format_paper(paper: Paper, index: int, markdown: bool = False) -> str:
    published = paper.published_date.isoformat() if paper.published_date else "desconhecido"
    authors = ", ".join(paper.authors) if paper.authors else "nao informado"
    doi = paper.doi or "nao encontrado"
    pdf_status = "disponivel" if paper.pdf_url else "nao encontrado"
    link = paper.url or "nao encontrado"

    if markdown:
        title = _escape_markdown(paper.title)
        source = _escape_markdown(paper.source)
        published = _escape_markdown(published)
        authors = _escape_markdown(authors)
        doi = _escape_markdown(doi)
        pdf_status = _escape_markdown(pdf_status)
        link = _escape_markdown(link)
    else:
        title = paper.title

    return (
        f"{index}. {title}\n"
        f"Fonte: {source if markdown else paper.source}\n"
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
    markdown: bool = False,
) -> list[str]:
    if not papers:
        return []

    effective_date = run_date or datetime.now().date()
    if markdown:
        header = (
            f"*Novidades em Paleopalinologia* \\- {_escape_markdown(effective_date.strftime('%d/%m/%Y'))}\n\n"
            f"Encontrei *{len(papers)}* possiveis novidades\\."
        )
    else:
        header = (
            f"Novidades em Paleopalinologia - {effective_date.strftime('%d/%m/%Y')}\n\n"
            f"Encontrei {len(papers)} possiveis novidades."
        )

    messages: list[str] = []
    for start in range(0, len(papers), max_items_per_message):
        chunk = papers[start : start + max_items_per_message]
        body = "\n\n".join(
            format_paper(paper, index, markdown=markdown)
            for index, paper in enumerate(chunk, start=start + 1)
        )
        messages.append(f"{header}\n\n{body}")

    return messages

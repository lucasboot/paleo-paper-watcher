from __future__ import annotations

from html import escape
from datetime import date, datetime

from src.models import Paper


def _format_links_html(paper: Paper) -> str:
    links: list[str] = []

    if paper.url:
        links.append(f'<a href="{escape(paper.url, quote=True)}">Artigo</a>')

    if paper.doi:
        doi_url = f"https://doi.org/{paper.doi}"
        links.append(f'<a href="{escape(doi_url, quote=True)}">DOI</a>')

    if paper.pdf_url:
        links.append(f'<a href="{escape(paper.pdf_url, quote=True)}">PDF</a>')

    return " | ".join(links) if links else "nao encontrado"


def format_paper(paper: Paper, index: int, html: bool = False) -> str:
    published = paper.published_date.isoformat() if paper.published_date else "desconhecido"
    authors = ", ".join(paper.authors) if paper.authors else "nao informado"
    doi = paper.doi or "nao encontrado"
    pdf_status = "disponivel" if paper.pdf_url else "nao encontrado"
    link = paper.url or "nao encontrado"

    if html:
        title = escape(paper.title)
        source = escape(paper.source)
        published = escape(published)
        authors = escape(authors)
        doi = escape(doi)
        pdf_status = escape(pdf_status)
        links = _format_links_html(paper)

        return (
            f"<b>{index}. {title}</b>\n"
            f"<b>Fonte:</b> {source}\n"
            f"<b>Publicado:</b> {published}\n"
            f"<b>Autores:</b> {authors}\n"
            f"<b>DOI:</b> {doi}\n"
            f"<b>PDF:</b> {pdf_status}\n"
            f"<b>Links:</b> {links}"
        )

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
    html: bool = False,
) -> list[str]:
    if not papers:
        return []

    effective_date = run_date or datetime.now().date()
    if html:
        header = (
            f"<b>📚 Novidades em Paleopalinologia</b> - {escape(effective_date.strftime('%d/%m/%Y'))}\n\n"
            f"Encontrei <b>{len(papers)}</b> possiveis novidades."
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
            format_paper(paper, index, html=html)
            for index, paper in enumerate(chunk, start=start + 1)
        )
        messages.append(f"{header}\n\n{body}")

    return messages

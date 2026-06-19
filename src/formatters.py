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
    summary = paper.summary_pt
    contribution = paper.summary_contribution
    limitations = paper.summary_limitations

    if html:
        title = escape(paper.title)
        source = escape(paper.source)
        published = escape(published)
        authors = escape(authors)
        doi = escape(doi)
        pdf_status = escape(pdf_status)
        links = _format_links_html(paper)
        summary = escape(summary) if summary else None
        contribution = escape(contribution) if contribution else None
        limitations = escape(limitations) if limitations else None
        lines = [
            f"<b>{index}. {title}</b>\n"
            f"<b>Fonte:</b> {source}",
            f"<b>Publicado:</b> {published}",
            f"<b>Autores:</b> {authors}",
            f"<b>DOI:</b> {doi}",
            f"<b>PDF:</b> {pdf_status}",
        ]
        if summary:
            lines.append(f"<b>Resumo:</b> {summary}")
        if contribution:
            lines.append(f"<b>Contribuicao:</b> {contribution}")
        if limitations:
            lines.append(f"<b>Limitacao:</b> {limitations}")
        lines.append(f"<b>Links:</b> {links}")
        return "\n".join(lines)

    lines = [
        f"{index}. {paper.title}",
        f"Fonte: {paper.source}",
        f"Publicado: {published}",
        f"Autores: {authors}",
        f"DOI: {doi}",
        f"PDF: {pdf_status}",
    ]
    if summary:
        lines.append(f"Resumo: {summary}")
    if contribution:
        lines.append(f"Contribuicao: {contribution}")
    if limitations:
        lines.append(f"Limitacao: {limitations}")
    lines.append(f"Link: {link}")
    return "\n".join(lines)


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

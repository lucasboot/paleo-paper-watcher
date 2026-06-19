from __future__ import annotations

import logging
import os

from openai import AsyncOpenAI
from pydantic import BaseModel

from src.models import Paper

LOGGER = logging.getLogger(__name__)

PROMPT_TEMPLATE = """Voce e um assistente cientifico especializado em resumir artigos academicos para acompanhamento bibliografico.

Tarefa:
Gere um resumo curto em {summary_language} sobre o artigo abaixo.

Regras:
- Use apenas as informacoes fornecidas.
- Nao invente resultados, metodos, conclusoes, amostras, localidades ou periodos geologicos que nao estejam explicitos.
- Se o abstract for curto, vago ou ausente, diga que a interpretacao e limitada.
- Mantenha linguagem clara para uma pessoa da area de Paleopalinologia.
- Nao traduza nomes proprios de forma artificial.
- Preserve termos tecnicos importantes quando fizer sentido.
- Seja objetivo.

Responda somente em JSON valido, neste formato:
{{
  "resumo": "2 a 4 frases resumindo o artigo.",
  "contribuicao": "1 frase explicando por que esse artigo pode ser relevante para Paleopalinologia.",
  "limitacoes": "1 frase sobre limitacoes do resumo com base nos dados disponiveis, ou string vazia se nao houver limitacao evidente.",
  "confianca": "alta | media | baixa"
}}

Dados do artigo:
Titulo: {title}
Autores: {authors}
Fonte: {source}
Periodico/venue: {venue}
Data de publicacao: {published_date}
DOI: {doi}
Abstract:

{abstract}
"""


class SummaryResult(BaseModel):
    resumo: str
    contribuicao: str
    limitacoes: str
    confianca: str


def _build_prompt(paper: Paper, summary_language: str) -> str:
    return PROMPT_TEMPLATE.format(
        summary_language=summary_language,
        title=paper.title,
        authors=", ".join(paper.authors) if paper.authors else "nao informado",
        source=paper.source,
        venue=paper.venue or "nao informado",
        published_date=paper.published_date.isoformat() if paper.published_date else "nao informado",
        doi=paper.doi or "nao informado",
        abstract=paper.abstract or "",
    )


def _apply_summary(paper: Paper, result: SummaryResult) -> Paper:
    return paper.model_copy(
        update={
            "summary_pt": result.resumo.strip() or None,
            "summary_contribution": result.contribuicao.strip() or None,
            "summary_limitations": result.limitacoes.strip() or None,
            "summary_confidence": result.confianca.strip().lower() or None,
        }
    )


def _response_debug_text(response) -> str:
    output_text = (response.output_text or "").strip()
    if output_text:
        return output_text[:500]

    try:
        serialized = response.to_json()
    except Exception:
        serialized = repr(response)

    return serialized[:500]


async def summarize_paper(
    paper: Paper,
    model: str,
    client: AsyncOpenAI,
    summary_language: str,
    reasoning_effort: str,
    max_output_tokens: int,
) -> Paper:
    if not paper.abstract:
        return paper
    try:
        response = await client.responses.parse(
            model=model,
            store=False,
            instructions="Responda somente em JSON valido.",
            input=_build_prompt(paper, summary_language),
            text_format=SummaryResult,
            reasoning={"effort": reasoning_effort},
            max_output_tokens=max_output_tokens,
        )
    except Exception as exc:
        LOGGER.warning("OpenAI summarization failed for paper=%r: %s", paper.title, exc)
        return paper

    result = response.output_parsed
    if result is None:
        incomplete_reason = getattr(getattr(response, "incomplete_details", None), "reason", None)
        if incomplete_reason == "max_output_tokens":
            LOGGER.warning(
                "OpenAI summarization hit max_output_tokens for paper=%r. Consider increasing openai.max_output_tokens. Raw response: %s",
                paper.title,
                _response_debug_text(response),
            )
            return paper

        LOGGER.warning(
            "OpenAI summarization returned no parsed output for paper=%r. Raw response: %s",
            paper.title,
            _response_debug_text(response),
        )
        return paper

    if result.confianca.strip().lower() not in {"alta", "media", "baixa"}:
        LOGGER.warning("OpenAI summarization returned invalid confidence for paper=%r", paper.title)
        return paper

    return _apply_summary(paper, result)


async def summarize_papers(papers: list[Paper], config) -> list[Paper]:
    if not config.openai.enabled:
        return papers

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return papers

    max_summaries = config.openai.max_summaries_per_run
    remaining = max_summaries if max_summaries > 0 else None
    client = AsyncOpenAI(api_key=api_key)

    summarized: list[Paper] = []
    for paper in papers:
        if not paper.abstract:
            summarized.append(paper)
            continue

        if remaining is not None and remaining <= 0:
            summarized.append(paper)
            continue

        summarized_paper = await summarize_paper(
            paper=paper,
            model=config.openai.model,
            client=client,
            summary_language=config.openai.summary_language,
            reasoning_effort=config.openai.reasoning_effort,
            max_output_tokens=config.openai.max_output_tokens,
        )
        summarized.append(summarized_paper)

        if remaining is not None:
            remaining -= 1

    return summarized

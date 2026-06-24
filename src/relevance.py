from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum
import re

from src.config import FiltersConfig
from src.models import Paper

TOKEN_PATTERN = re.compile(r"\b[\w-]+\b", re.UNICODE)
SPACE_PATTERN = re.compile(r"\s+")


class RelevanceCategory(StrEnum):
    DIRECT_THESIS_RELEVANCE = "direct_thesis_relevance"
    METHODOLOGICAL_ANALOG = "methodological_analog"
    REJECTED = "rejected"


@dataclass(frozen=True)
class TextMatchContext:
    normalized_text: str
    tokens: set[str]


@dataclass(frozen=True)
class RelevanceDecision:
    direct_score: int
    methodological_score: int
    final_score: int
    category: RelevanceCategory
    reasons: list[str]
    positive_reasons: list[str]
    negative_reasons: list[str]
    matched_regional_terms: list[str]
    matched_temporal_terms: list[str]
    matched_methodological_terms: list[str]
    matched_geoscience_context_terms: list[str]
    matched_negative_terms: list[str]
    approved: bool


def _normalize_text(value: str | None, *, remove_accents: bool) -> str:
    text = (value or "").casefold()
    if remove_accents:
        decomposed = unicodedata.normalize("NFKD", text)
        text = "".join(char for char in decomposed if not unicodedata.combining(char))

    collapsed = re.sub(r"[^\w\s-]+", " ", text, flags=re.UNICODE)
    return SPACE_PATTERN.sub(" ", collapsed).strip()


def _build_context(value: str | None, *, remove_accents: bool) -> TextMatchContext:
    normalized_text = _normalize_text(value, remove_accents=remove_accents)
    return TextMatchContext(
        normalized_text=normalized_text,
        tokens=set(TOKEN_PATTERN.findall(normalized_text)),
    )


def _normalize_term(term: str, *, remove_accents: bool) -> str:
    return _normalize_text(term, remove_accents=remove_accents)


def _term_matches(term: str, context: TextMatchContext, *, remove_accents: bool) -> bool:
    normalized_term = _normalize_term(term, remove_accents=remove_accents)
    if not normalized_term:
        return False

    parts = normalized_term.split()
    if len(parts) == 1:
        token = parts[0]
        return token in context.tokens

    return normalized_term in context.normalized_text


def _match_terms(
    context: TextMatchContext,
    terms: list[str] | tuple[str, ...],
    *,
    remove_accents: bool,
) -> list[str]:
    matches: list[str] = []
    for term in terms:
        normalized_term = _normalize_term(term, remove_accents=remove_accents)
        if not normalized_term:
            continue
        if _term_matches(term, context, remove_accents=remove_accents) and term not in matches:
            matches.append(term)
    return matches


def build_search_text(paper: Paper) -> str:
    return " ".join(
        part.strip()
        for part in (paper.title or "", paper.abstract or "", paper.venue or "", " ".join(paper.authors))
        if part and part.strip()
    )


def _append_reason(reasons: list[str], score: int, label: str, matches: list[str]) -> int:
    if not matches:
        return 0

    reasons.append(f"{score:+d} {label}: {', '.join(matches)}")
    return score


def _has_methodological_anchor(methodological_title_matches: list[str], methodological_abstract_matches: list[str]) -> bool:
    return bool(methodological_title_matches or methodological_abstract_matches)


def _summarize_main_matches(decision: RelevanceDecision) -> list[str]:
    ordered = (
        decision.matched_regional_terms
        + decision.matched_temporal_terms
        + decision.matched_methodological_terms
        + decision.matched_geoscience_context_terms
    )

    unique: list[str] = []
    for term in ordered:
        if term not in unique:
            unique.append(term)
    return unique[:5]


def evaluate_relevance(paper: Paper, filters_config: FiltersConfig) -> RelevanceDecision:
    remove_accents = filters_config.normalize.remove_accents
    title_context = _build_context(paper.title, remove_accents=remove_accents)
    abstract_context = _build_context(paper.abstract, remove_accents=remove_accents)
    venue_context = _build_context(paper.venue, remove_accents=remove_accents)
    authors_context = _build_context(" ".join(paper.authors), remove_accents=remove_accents)
    search_context = _build_context(build_search_text(paper), remove_accents=remove_accents)

    regional_title_matches = _match_terms(title_context, filters_config.regional_keywords, remove_accents=remove_accents)
    regional_abstract_matches = _match_terms(abstract_context, filters_config.regional_keywords, remove_accents=remove_accents)
    temporal_title_matches = _match_terms(title_context, filters_config.temporal_keywords, remove_accents=remove_accents)
    temporal_abstract_matches = _match_terms(abstract_context, filters_config.temporal_keywords, remove_accents=remove_accents)
    methodological_title_matches = _match_terms(
        title_context,
        filters_config.methodological_keywords,
        remove_accents=remove_accents,
    )
    methodological_abstract_matches = _match_terms(
        abstract_context,
        filters_config.methodological_keywords,
        remove_accents=remove_accents,
    )
    methodological_venue_matches = _match_terms(
        venue_context,
        filters_config.methodological_keywords,
        remove_accents=remove_accents,
    )
    geoscience_title_matches = _match_terms(
        title_context,
        filters_config.geoscience_context_keywords,
        remove_accents=remove_accents,
    )
    geoscience_abstract_matches = _match_terms(
        abstract_context,
        filters_config.geoscience_context_keywords,
        remove_accents=remove_accents,
    )
    geoscience_venue_matches = _match_terms(
        venue_context,
        filters_config.geoscience_context_keywords,
        remove_accents=remove_accents,
    )
    venue_matches = _match_terms(venue_context, filters_config.preferred_venues, remove_accents=remove_accents)
    author_matches = _match_terms(authors_context, filters_config.preferred_authors, remove_accents=remove_accents)
    negative_matches = _match_terms(search_context, filters_config.negative_keywords, remove_accents=remove_accents)

    direct_positive_reasons: list[str] = []
    methodological_positive_reasons: list[str] = []
    negative_reasons: list[str] = []

    direct_score = 0
    direct_score += _append_reason(direct_positive_reasons, 8, "regional no titulo", regional_title_matches)
    direct_score += _append_reason(direct_positive_reasons, 6, "regional no resumo", regional_abstract_matches)
    direct_score += _append_reason(direct_positive_reasons, 5, "temporal no titulo", temporal_title_matches)
    direct_score += _append_reason(direct_positive_reasons, 3, "temporal no resumo", temporal_abstract_matches)
    direct_score += _append_reason(direct_positive_reasons, 5, "metodo no titulo", methodological_title_matches)
    direct_score += _append_reason(direct_positive_reasons, 3, "metodo no resumo", methodological_abstract_matches)
    direct_score += _append_reason(direct_positive_reasons, 2, "periodico preferido", venue_matches)
    direct_score += _append_reason(direct_positive_reasons, 2, "autor preferido", author_matches)

    methodological_score = 0
    methodological_score += _append_reason(methodological_positive_reasons, 5, "metodo no titulo", methodological_title_matches)
    methodological_score += _append_reason(methodological_positive_reasons, 3, "metodo no resumo", methodological_abstract_matches)
    methodological_score += _append_reason(methodological_positive_reasons, 3, "contexto geocientifico no titulo", geoscience_title_matches)
    methodological_score += _append_reason(methodological_positive_reasons, 2, "contexto geocientifico no resumo", geoscience_abstract_matches)
    methodological_score += _append_reason(methodological_positive_reasons, 2, "periodico preferido", venue_matches)
    methodological_score += _append_reason(methodological_positive_reasons, 2, "autor preferido", author_matches)

    for term in negative_matches:
        direct_score -= 6
        methodological_score -= 6
        negative_reasons.append(f"-6 negativo: {term}")

    has_direct_anchor = bool(regional_title_matches or regional_abstract_matches or temporal_title_matches or temporal_abstract_matches)
    has_methodological_anchor = _has_methodological_anchor(methodological_title_matches, methodological_abstract_matches)

    if negative_matches and not (has_direct_anchor or has_methodological_anchor):
        direct_score -= 10
        methodological_score -= 10
        negative_reasons.append("-10 negativo sem ancora regional/temporal/metodologica")

    direct_config = filters_config.direct_thesis
    direct_passes = (
        direct_config.enabled
        and direct_score >= direct_config.min_score
        and has_direct_anchor
    )
    if direct_config.require_anchor and not has_direct_anchor:
        direct_passes = False

    matched_methodological_terms = []
    for term in methodological_title_matches + methodological_abstract_matches + methodological_venue_matches:
        if term not in matched_methodological_terms:
            matched_methodological_terms.append(term)

    matched_geoscience_terms = []
    for term in geoscience_title_matches + geoscience_abstract_matches + geoscience_venue_matches:
        if term not in matched_geoscience_terms:
            matched_geoscience_terms.append(term)

    analog_config = filters_config.methodological_analog
    has_geoscience_context = bool(matched_geoscience_terms)
    methodological_passes = (
        analog_config.enabled
        and methodological_score >= analog_config.min_score
        and len(matched_methodological_terms) >= analog_config.min_methodological_terms
        and (has_geoscience_context or not analog_config.require_geoscience_context)
        and not (negative_matches and not has_methodological_anchor)
    )

    if not filters_config.enabled:
        category = RelevanceCategory.DIRECT_THESIS_RELEVANCE
        approved = True
        final_score = direct_score
    elif direct_passes:
        category = RelevanceCategory.DIRECT_THESIS_RELEVANCE
        approved = True
        final_score = direct_score
    elif methodological_passes:
        category = RelevanceCategory.METHODOLOGICAL_ANALOG
        approved = True
        final_score = methodological_score
    else:
        category = RelevanceCategory.REJECTED
        approved = False
        final_score = max(direct_score, methodological_score)

    positive_reasons = direct_positive_reasons if category != RelevanceCategory.METHODOLOGICAL_ANALOG else methodological_positive_reasons
    reasons = positive_reasons + negative_reasons
    if approved and not reasons:
        reasons = ["aprovado sem motivos destacados"]

    return RelevanceDecision(
        direct_score=direct_score,
        methodological_score=methodological_score,
        final_score=final_score,
        category=category,
        reasons=reasons,
        positive_reasons=positive_reasons,
        negative_reasons=negative_reasons,
        matched_regional_terms=regional_title_matches + [term for term in regional_abstract_matches if term not in regional_title_matches],
        matched_temporal_terms=temporal_title_matches + [term for term in temporal_abstract_matches if term not in temporal_title_matches],
        matched_methodological_terms=matched_methodological_terms,
        matched_geoscience_context_terms=matched_geoscience_terms,
        matched_negative_terms=negative_matches,
        approved=approved,
    )


def calculate_relevance_score(paper: Paper, filters_config: FiltersConfig) -> tuple[int, list[str]]:
    decision = evaluate_relevance(paper, filters_config)
    return decision.final_score, decision.reasons


def is_relevant(paper: Paper, filters_config: FiltersConfig) -> bool:
    if not filters_config.enabled:
        return True
    return evaluate_relevance(paper, filters_config).approved


def summarize_decision(decision: RelevanceDecision) -> str:
    if decision.category == RelevanceCategory.DIRECT_THESIS_RELEVANCE:
        category_label = "relação direta com a tese"
    elif decision.category == RelevanceCategory.METHODOLOGICAL_ANALOG:
        category_label = "análogo metodológico"
    else:
        category_label = "rejeitado"

    motives = ", ".join(_summarize_main_matches(decision)) or "sem termos destacados"
    return f"Categoria: {category_label} | Score: {decision.final_score} | Motivos: {motives}"

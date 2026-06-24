from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from src.config import FiltersConfig
from src.models import Paper

CORE_BASIN_TERMS = ("Alagamar", "Alagamar Formation", "Formação Alagamar", "Potiguar Basin", "Bacia Potiguar")
UNIT_TERMS = ("Upanema", "Ponta do Tubarão", "Galinhos", "Canto do Amaro")
METHOD_TERMS = ("palynofacies", "palinofácies", "palynology", "palinologia", "palynomorphs")
INTERVAL_TERMS = ("Aptian", "Aptiano", "Albian", "Albiano", "Lower Cretaceous", "Cretáceo Inferior")
GEOCHEM_TERMS = (
    "organic geochemistry",
    "geoquímica orgânica",
    "biomarkers",
    "biomarcadores",
    "TOC",
    "COT",
    "Rock-Eval",
    "thermal maturation",
)


@dataclass(frozen=True)
class RelevanceDecision:
    score: int
    reasons: list[str]
    positive_reasons: list[str]
    negative_reasons: list[str]
    has_anchor: bool
    strong_geology_match_count: int
    has_negative: bool
    approved: bool


def _normalize_text(value: str | None) -> str:
    text = (value or "").casefold()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _match_terms(text: str, terms: list[str] | tuple[str, ...]) -> list[str]:
    matches: list[str] = []
    for term in terms:
        normalized_term = _normalize_text(term)
        if normalized_term and normalized_term in text and term not in matches:
            matches.append(term)
    return matches


def build_search_text(paper: Paper) -> str:
    return " ".join(
        part.strip()
        for part in (paper.title or "", paper.abstract or "", paper.venue or "", " ".join(paper.authors))
        if part and part.strip()
    )


def evaluate_relevance(paper: Paper, filters_config: FiltersConfig) -> RelevanceDecision:
    normalized_title = _normalize_text(paper.title)
    normalized_abstract = _normalize_text(paper.abstract)
    normalized_venue = _normalize_text(paper.venue)
    normalized_authors = _normalize_text(" ".join(paper.authors))
    normalized_search_text = _normalize_text(build_search_text(paper))

    score = 0
    positive_reasons: list[str] = []
    negative_reasons: list[str] = []

    title_core_matches = _match_terms(normalized_title, CORE_BASIN_TERMS)
    if title_core_matches:
        score += 8
        positive_reasons.append(f"+8 nucleo no titulo: {', '.join(title_core_matches)}")

    abstract_core_matches = _match_terms(normalized_abstract, CORE_BASIN_TERMS)
    if abstract_core_matches:
        score += 6
        positive_reasons.append(f"+6 nucleo no resumo: {', '.join(abstract_core_matches)}")

    title_unit_matches = _match_terms(normalized_title, UNIT_TERMS)
    if title_unit_matches:
        score += 5
        positive_reasons.append(f"+5 unidade no titulo: {', '.join(title_unit_matches)}")

    title_method_matches = _match_terms(normalized_title, METHOD_TERMS)
    if title_method_matches:
        score += 5
        positive_reasons.append(f"+5 metodo no titulo: {', '.join(title_method_matches)}")

    abstract_method_matches = _match_terms(normalized_abstract, METHOD_TERMS)
    if abstract_method_matches:
        score += 3
        positive_reasons.append(f"+3 metodo no resumo: {', '.join(abstract_method_matches)}")

    interval_matches = _match_terms(normalized_search_text, INTERVAL_TERMS)
    if interval_matches:
        score += 3
        positive_reasons.append(f"+3 intervalo: {', '.join(interval_matches)}")

    geochem_matches = _match_terms(normalized_search_text, GEOCHEM_TERMS)
    if geochem_matches:
        score += 2
        positive_reasons.append(f"+2 geoquimica/proxy: {', '.join(geochem_matches)}")

    venue_matches = _match_terms(normalized_venue, filters_config.preferred_venues)
    if venue_matches:
        score += 2
        positive_reasons.append(f"+2 periodico preferido: {', '.join(venue_matches)}")

    author_matches = _match_terms(normalized_authors, filters_config.preferred_authors)
    if author_matches:
        score += 2
        positive_reasons.append(f"+2 autor preferido: {', '.join(author_matches)}")

    geology_matches = _match_terms(normalized_search_text, filters_config.geology_keywords)
    strong_geology_matches = _match_terms(normalized_search_text, filters_config.strong_geology_keywords)

    negative_matches = _match_terms(normalized_search_text, filters_config.negative_keywords)
    for term in negative_matches:
        score -= 6
        negative_reasons.append(f"-6 negativo: {term}")

    anchor_title_matches = _match_terms(normalized_title, filters_config.anchor_keywords)
    anchor_abstract_matches = _match_terms(normalized_abstract, filters_config.anchor_keywords)
    has_anchor = bool(anchor_title_matches or anchor_abstract_matches)

    if negative_matches and not has_anchor:
        score -= 10
        negative_reasons.append("-10 negativo sem anchor")

    meets_score = score >= filters_config.min_score
    meets_anchor_path = meets_score and has_anchor
    meets_strong_geology_path = meets_score and len(strong_geology_matches) >= 2 and not negative_matches
    approved = meets_anchor_path or meets_strong_geology_path or not filters_config.enabled

    if filters_config.enabled and filters_config.require_anchor and not has_anchor and not meets_strong_geology_path:
        approved = False

    reasons = positive_reasons + negative_reasons
    if geology_matches and not positive_reasons:
        reasons.insert(0, f"geologia detectada: {', '.join(geology_matches[:5])}")

    return RelevanceDecision(
        score=score,
        reasons=reasons,
        positive_reasons=positive_reasons,
        negative_reasons=negative_reasons,
        has_anchor=has_anchor,
        strong_geology_match_count=len(strong_geology_matches),
        has_negative=bool(negative_matches),
        approved=approved,
    )


def calculate_relevance_score(paper: Paper, filters_config: FiltersConfig) -> tuple[int, list[str]]:
    decision = evaluate_relevance(paper, filters_config)
    return decision.score, decision.reasons


def is_relevant(paper: Paper, filters_config: FiltersConfig) -> bool:
    if not filters_config.enabled:
        return True
    return evaluate_relevance(paper, filters_config).approved

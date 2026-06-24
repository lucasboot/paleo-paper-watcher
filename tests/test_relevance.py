from __future__ import annotations

import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from main import apply_relevance_filters, build_relevance_summaries, log_filtered_papers
from src.config import FiltersConfig, load_config
from src.formatters import format_daily_messages
from src.models import Paper
from src.normalize import dedupe_key
from src.relevance import (
    RelevanceCategory,
    build_search_text,
    calculate_relevance_score,
    evaluate_relevance,
    is_relevant,
)


class RelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filters = FiltersConfig.model_validate(
            {
                "enabled": True,
                "normalize": {"remove_accents": True},
                "direct_thesis": {
                    "enabled": True,
                    "min_score": 7,
                    "require_anchor": True,
                },
                "methodological_analog": {
                    "enabled": True,
                    "min_score": 10,
                    "min_methodological_terms": 3,
                    "require_geoscience_context": True,
                },
                "regional_keywords": [
                    "Alagamar",
                    "Alagamar Formation",
                    "Formação Alagamar",
                    "Potiguar Basin",
                    "Bacia Potiguar",
                    "Upanema Member",
                    "Canto do Amaro",
                ],
                "temporal_keywords": [
                    "Aptian",
                    "Aptiano",
                    "Albian",
                    "Albiano",
                    "Aptian-Albian",
                    "Lower Cretaceous",
                    "Cretáceo Inferior",
                ],
                "methodological_keywords": [
                    "palynofacies",
                    "palinofácies",
                    "palynology",
                    "palinologia",
                    "organic geochemistry",
                    "TOC",
                    "COT",
                    "Rock-Eval",
                    "source rock",
                    "biostratigraphy",
                    "marine transgression",
                ],
                "geoscience_context_keywords": [
                    "geology",
                    "stratigraphy",
                    "sedimentology",
                    "sedimentary basin",
                    "basin",
                    "formation",
                    "shale",
                    "source rock",
                    "petroleum",
                    "hydrocarbon",
                    "paleoenvironment",
                    "organic matter",
                ],
                "preferred_venues": ["Marine and Petroleum Geology"],
                "preferred_authors": ["Rodolfo Dino"],
                "negative_keywords": [
                    "education",
                    "medical",
                    "medicine",
                    "allergy",
                    "agriculture",
                    "agricultural",
                    "crop production",
                    "crop management",
                    "crop yield",
                    "farming",
                    "contexto educacional",
                    "autocuidado",
                    "Mars",
                ],
            }
        )

    def test_build_search_text_concatenates_fields(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="1",
            title="Alagamar Formation palynofacies",
            abstract="Organic geochemistry in the Aptian.",
            venue="Marine and Petroleum Geology",
            authors=["Rodolfo Dino"],
        )

        self.assertEqual(
            build_search_text(paper),
            "Alagamar Formation palynofacies Organic geochemistry in the Aptian. Marine and Petroleum Geology Rodolfo Dino",
        )

    def test_direct_relevance_category_for_alagamar_article(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="2",
            title="Alagamar Formation palynology",
            abstract="Lower Cretaceous interval in the Potiguar Basin.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.category, RelevanceCategory.DIRECT_THESIS_RELEVANCE)
        self.assertTrue(decision.approved)
        self.assertGreaterEqual(decision.direct_score, 7)

    def test_methodological_analog_passes_without_regional_anchor(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="3",
            title="Devonian strata of the Amazonas Basin: Organic geochemistry and palynofacies of shales",
            abstract="Source rock evaluation with TOC and Rock-Eval for hydrocarbon generation in a sedimentary basin.",
            venue="Organic Geochemistry",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.category, RelevanceCategory.METHODOLOGICAL_ANALOG)
        self.assertTrue(decision.approved)
        self.assertGreaterEqual(len(decision.matched_methodological_terms), 5)
        self.assertTrue(decision.matched_geoscience_context_terms)

    def test_crop_does_not_match_outcrop(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="4",
            title="Organic geochemistry and palynofacies of outcrops",
            abstract="TOC and Rock-Eval source rock data from a sedimentary basin.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("crop production", decision.matched_negative_terms)
        self.assertEqual(decision.category, RelevanceCategory.METHODOLOGICAL_ANALOG)

    def test_toc_does_not_match_autocuidado(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="5",
            title="Education and medicine",
            abstract="Praticas de autocuidado no contexto hospitalar.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("TOC", decision.matched_methodological_terms)
        self.assertFalse(decision.approved)

    def test_cot_does_not_match_contexto(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="6",
            title="Contexto educacional e formacao docente",
            abstract="Study in school settings.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("COT", decision.matched_methodological_terms)
        self.assertFalse(decision.approved)

    def test_cot_does_not_match_cotidiano(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="7",
            title="Cotidiano escolar e aprendizagem",
            abstract="Education research.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("COT", decision.matched_methodological_terms)
        self.assertFalse(decision.approved)

    def test_toc_matches_isolated_token(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="8",
            title="TOC values in a source rock",
            abstract="Sedimentary basin analysis.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertIn("TOC", decision.matched_methodological_terms)

    def test_cot_matches_isolated_token(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="9",
            title="COT total em rocha geradora",
            abstract="Basin stratigraphy.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertIn("COT", decision.matched_methodological_terms)

    def test_medical_education_article_does_not_get_toc_points_from_autocuidado(self) -> None:
        paper = Paper(
            source="semantic_scholar",
            external_id="10",
            title="Medical education in nursing",
            abstract="Autocuidado e ensino em sala de aula.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("TOC", decision.matched_methodological_terms)
        self.assertLess(decision.methodological_score, 0)

    def test_contexto_educacional_article_does_not_get_cot_points(self) -> None:
        paper = Paper(
            source="semantic_scholar",
            external_id="11",
            title="Contexto educacional e curriculo",
            abstract="Teacher training and classroom practices.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertNotIn("COT", decision.matched_methodological_terms)
        self.assertFalse(decision.approved)

    def test_agriculture_article_with_crop_production_is_rejected(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="12",
            title="Crop production under climate stress",
            abstract="Agricultural management and farming practices.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.category, RelevanceCategory.REJECTED)
        self.assertIn("crop production", decision.matched_negative_terms)

    def test_accent_and_case_insensitive_matching(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="13",
            title="FORMACAO ALAGAMAR E PALYNOFACIES",
            abstract="Transgressao marinha no Aptiano.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.category, RelevanceCategory.DIRECT_THESIS_RELEVANCE)
        self.assertIn("Formação Alagamar", decision.matched_regional_terms)
        self.assertIn("Aptiano", decision.matched_temporal_terms)

    def test_preferred_venue_and_author_boost_score(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="14",
            title="palynofacies of a marginal basin",
            abstract="TOC and Rock-Eval in a source rock.",
            venue="Marine and Petroleum Geology",
            authors=["Rodolfo Dino", "Outro Autor"],
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertIn("+2 periodico preferido: Marine and Petroleum Geology", decision.positive_reasons)
        self.assertIn("+2 autor preferido: Rodolfo Dino", decision.positive_reasons)

    def test_priority_prefers_direct_relevance_when_both_pass(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="15",
            title="Alagamar Formation palynofacies and organic geochemistry",
            abstract="TOC, Rock-Eval and source rock characterization in the Aptian basin.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.category, RelevanceCategory.DIRECT_THESIS_RELEVANCE)
        self.assertTrue(decision.direct_score >= self.filters.direct_thesis.min_score)
        self.assertTrue(decision.methodological_score >= self.filters.methodological_analog.min_score)

    def test_calculate_relevance_score_returns_final_score(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="16",
            title="Alagamar Formation palynofacies",
            abstract="Aptian source rock interval.",
        )

        score, reasons = calculate_relevance_score(paper, self.filters)

        self.assertEqual(score, evaluate_relevance(paper, self.filters).final_score)
        self.assertTrue(reasons)

    def test_missing_new_filter_fields_use_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "queries:\n"
                "  - test\n"
                "filters:\n"
                "  enabled: true\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertTrue(config.filters.normalize.remove_accents)
        self.assertEqual(config.filters.methodological_analog.min_methodological_terms, 3)
        self.assertTrue(config.filters.direct_thesis.require_anchor)

    def test_apply_relevance_filters_returns_decisions_map(self) -> None:
        approved_paper = Paper(
            source="openalex",
            external_id="17",
            title="Alagamar Formation palynofacies",
            abstract="Aptian interval with TOC.",
        )
        rejected_paper = Paper(
            source="arxiv",
            external_id="18",
            title="Education on Mars",
            abstract="",
        )

        approved, rejected, decisions = apply_relevance_filters(
            [approved_paper, rejected_paper],
            enabled=True,
            filters_config=self.filters,
        )

        self.assertEqual(approved, [approved_paper])
        self.assertEqual(len(rejected), 1)
        self.assertIn(dedupe_key(approved_paper), decisions)
        self.assertIn(dedupe_key(rejected_paper), decisions)

    def test_log_filtered_papers_prints_scores_category_and_reasons(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="19",
            title="Education on Mars",
            abstract="",
        )
        decision = evaluate_relevance(paper, self.filters)

        with patch("sys.stdout", new=StringIO()) as stdout:
            log_filtered_papers([(paper, decision)])

        output = stdout.getvalue()
        self.assertIn("direct_score=", output)
        self.assertIn("methodological_score=", output)
        self.assertIn("categoria=rejected", output)
        self.assertIn("negativos:", output)

    def test_format_daily_messages_includes_category_score_and_motives(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="20",
            title="Alagamar Formation palynofacies",
            abstract="Aptian interval.",
        )
        decision = evaluate_relevance(paper, self.filters)
        summaries = build_relevance_summaries({dedupe_key(paper): decision})

        plain_message = format_daily_messages(
            [paper],
            max_items_per_message=10,
            html=False,
            relevance_by_paper=summaries,
        )[0]
        html_message = format_daily_messages(
            [paper],
            max_items_per_message=10,
            html=True,
            relevance_by_paper=summaries,
        )[0]

        self.assertIn("Categoria: relação direta com a tese", plain_message)
        self.assertIn("Score:", plain_message)
        self.assertIn("Motivos:", plain_message)
        self.assertIn("Categoria: relação direta com a tese", html_message)

    def test_build_relevance_summaries_uses_category_and_main_matches(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="21",
            title="Alagamar Formation palynofacies",
            abstract="Aptian marine transgression with TOC.",
        )
        decision = evaluate_relevance(paper, self.filters)

        summaries = build_relevance_summaries({dedupe_key(paper): decision})

        self.assertIn("Categoria:", summaries[dedupe_key(paper)])
        self.assertIn("Score:", summaries[dedupe_key(paper)])
        self.assertIn("Motivos:", summaries[dedupe_key(paper)])

    def test_is_relevant_returns_true_for_methodological_analog(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="22",
            title="Palynofacies and organic geochemistry of shale source rock",
            abstract="TOC and Rock-Eval data from a sedimentary basin.",
        )

        self.assertTrue(is_relevant(paper, self.filters))


if __name__ == "__main__":
    unittest.main()

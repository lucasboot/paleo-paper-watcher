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
from src.relevance import build_search_text, calculate_relevance_score, evaluate_relevance, is_relevant


class RelevanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.filters = FiltersConfig(
            enabled=True,
            min_score=7,
            require_anchor=True,
            anchor_keywords=[
                "Alagamar Formation",
                "Potiguar Basin",
                "palynofacies",
                "Aptian",
            ],
            geology_keywords=[
                "marine transgression",
                "organic geochemistry",
                "Rock-Eval",
                "TOC",
                "biostratigraphy",
            ],
            strong_geology_keywords=[
                "marine transgression",
                "organic geochemistry",
                "Rock-Eval",
                "TOC",
            ],
            preferred_venues=["Marine and Petroleum Geology"],
            preferred_authors=["Rodolfo Dino"],
            negative_keywords=["education", "Mars", "allergy"],
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

    def test_core_basin_title_terms_receive_high_weight(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="2",
            title="Alagamar Formation in the Potiguar Basin",
            abstract="Aptian marine transgression and organic geochemistry.",
        )

        score, reasons = calculate_relevance_score(paper, self.filters)

        self.assertEqual(score, 13)
        self.assertIn("+8 nucleo no titulo: Alagamar, Alagamar Formation, Potiguar Basin", reasons)
        self.assertTrue(is_relevant(paper, self.filters))

    def test_preferred_venue_and_author_boost_score(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="3",
            title="palynofacies of a marginal basin",
            abstract="Aptian interval with Rock-Eval.",
            venue="Marine and Petroleum Geology",
            authors=["Rodolfo Dino", "Outro Autor"],
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.score, 14)
        self.assertIn("+2 periodico preferido: Marine and Petroleum Geology", decision.positive_reasons)
        self.assertIn("+2 autor preferido: Rodolfo Dino", decision.positive_reasons)
        self.assertTrue(decision.approved)

    def test_strong_geology_path_approves_without_anchor(self) -> None:
        paper = Paper(
            source="semantic_scholar",
            external_id="4",
            title="Marine transgression in a lower cretaceous basin",
            abstract="Organic geochemistry and TOC constraints for the section.",
            venue="Marine and Petroleum Geology",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertFalse(decision.has_anchor)
        self.assertEqual(decision.strong_geology_match_count, 3)
        self.assertTrue(decision.approved)

    def test_require_anchor_blocks_when_no_alternative_path(self) -> None:
        paper = Paper(
            source="semantic_scholar",
            external_id="5",
            title="Biostratigraphy of a lower cretaceous basin",
            abstract="General stratigraphic discussion.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertFalse(decision.has_anchor)
        self.assertFalse(decision.approved)

    def test_negative_keyword_without_anchor_gets_extra_penalty(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="6",
            title="Education on Mars",
            abstract="Allergy in classroom environments.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.score, -28)
        self.assertIn("-10 negativo sem anchor", decision.negative_reasons)
        self.assertFalse(decision.approved)

    def test_accent_and_case_insensitive_matching(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="7",
            title="FORMACAO ALAGAMAR E PALYNOFACIES",
            abstract="Transgressao marinha no Aptiano.",
        )

        decision = evaluate_relevance(paper, self.filters)

        self.assertEqual(decision.score, 16)
        self.assertIn("+8 nucleo no titulo: Alagamar, Formação Alagamar", decision.positive_reasons)
        self.assertIn("+5 metodo no titulo: palynofacies", decision.positive_reasons)
        self.assertIn("+3 intervalo: Aptian, Aptiano", decision.positive_reasons)

    def test_missing_new_filter_fields_use_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.yaml"
            config_path.write_text(
                "queries:\n"
                "  - test\n"
                "filters:\n"
                "  enabled: true\n"
                "  min_score: 7\n",
                encoding="utf-8",
            )

            config = load_config(config_path)

        self.assertEqual(config.filters.strong_geology_keywords, [])
        self.assertEqual(config.filters.preferred_venues, [])
        self.assertEqual(config.filters.preferred_authors, [])

    def test_apply_relevance_filters_returns_decisions_map(self) -> None:
        approved_paper = Paper(
            source="openalex",
            external_id="8",
            title="Alagamar Formation palynofacies",
            abstract="Aptian interval with TOC.",
        )
        rejected_paper = Paper(
            source="arxiv",
            external_id="9",
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

    def test_log_filtered_papers_prints_positive_and_negative_reasons(self) -> None:
        paper = Paper(
            source="crossref",
            external_id="10",
            title="Education on Mars",
            abstract="",
        )
        decision = evaluate_relevance(paper, self.filters)

        with patch("sys.stdout", new=StringIO()) as stdout:
            log_filtered_papers([(paper, decision)])

        output = stdout.getvalue()
        self.assertIn("1 artigo(s) filtrado(s) por relevancia:", output)
        self.assertIn("positivos: nenhum", output)
        self.assertIn("negativos: -6 negativo: education; -6 negativo: Mars; -10 negativo sem anchor", output)

    def test_format_daily_messages_includes_relevance_summary(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="11",
            title="Alagamar Formation palynofacies",
            abstract="Aptian interval.",
        )
        summaries = {dedupe_key(paper): "score 16 | +8 nucleo no titulo: Alagamar Formation"}

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

        self.assertIn("Relevancia: score 16 | +8 nucleo no titulo: Alagamar Formation", plain_message)
        self.assertIn("<b>Links:</b>", html_message)
        self.assertIn("Relevancia: score 16 | +8 nucleo no titulo: Alagamar Formation", html_message)

    def test_build_relevance_summaries_uses_top_reasons(self) -> None:
        paper = Paper(
            source="openalex",
            external_id="12",
            title="Alagamar Formation palynofacies",
            abstract="Aptian marine transgression with TOC.",
        )
        decision = evaluate_relevance(paper, self.filters)

        summaries = build_relevance_summaries({dedupe_key(paper): decision})

        self.assertIn("score", summaries[dedupe_key(paper)])
        self.assertIn("+8 nucleo no titulo", summaries[dedupe_key(paper)])


if __name__ == "__main__":
    unittest.main()

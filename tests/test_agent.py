"""End-to-end tests for the onboarding review graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.main import run_for
from src.models import Recommendation


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "candidates"


@pytest.mark.parametrize("candidate_id", ["ana_garcia", "marco_silva", "laura_mendez"])
def test_report_for_each_candidate_has_all_fields(candidate_id):
    report = run_for(candidate_id, data_dir=DATA_DIR)
    # Esquema
    for field in ("candidate", "competencies", "document_findings",
                  "red_flags", "overall_score", "recommendation",
                  "summary", "follow_up_questions"):
        assert field in report, f"missing '{field}' in report"
    # Ranges
    assert 0 <= report["overall_score"] <= 10
    assert len(report["competencies"]) == 6


def test_strong_candidate_gets_high_score():
    report = run_for("ana_garcia", data_dir=DATA_DIR)
    assert report["overall_score"] >= 6.5
    assert report["recommendation"] in {
        Recommendation.HIRE.value,
        Recommendation.STRONG_HIRE.value,
    }


def test_weak_candidate_gets_low_score():
    report = run_for("laura_mendez", data_dir=DATA_DIR)
    assert report["overall_score"] <= 5.5
    # Por red flags o por score bajo, no debería ser hire
    assert report["recommendation"] in {
        Recommendation.NO_HIRE.value,
        Recommendation.HIRE_WITH_CAVEATS.value,
    }


def test_middle_candidate_flags_gap():
    report = run_for("marco_silva", data_dir=DATA_DIR)
    flag_titles = [f["title"].lower() for f in report["red_flags"]]
    assert any("gap" in t for t in flag_titles), \
        f"expected a 'gap' red flag for Marco, got: {flag_titles}"


def test_competency_scores_are_in_valid_range():
    report = run_for("ana_garcia", data_dir=DATA_DIR)
    for comp in report["competencies"]:
        assert 0 <= comp["score"] <= 10
        assert comp["status"] in {"above_expected", "at_expected", "below_expected"}


# ----------------------------------------------------------------------
# Conditional branch: deep_dive fires only on borderline scores
# ----------------------------------------------------------------------


def test_strong_candidate_skips_deep_dive():
    """Ana scores high → deep_dive must NOT run → no follow-up questions."""
    report = run_for("ana_garcia", data_dir=DATA_DIR)
    assert report["overall_score"] > 6.5
    assert report["follow_up_questions"] == [], (
        "deep_dive should be skipped for high-score candidates"
    )


def test_borderline_candidate_triggers_deep_dive():
    """Marco lands in [5.5, 6.5] → deep_dive must run → follow-ups present."""
    report = run_for("marco_silva", data_dir=DATA_DIR)
    score = report["overall_score"]
    assert 5.5 <= score <= 6.5, (
        f"Marco should land in the borderline range; got {score}"
    )
    assert len(report["follow_up_questions"]) >= 2, (
        "deep_dive should produce 2-3 follow-up questions"
    )
    assert all(isinstance(q, str) and q for q in report["follow_up_questions"])


def test_weak_candidate_skips_deep_dive():
    """Laura scores below borderline → deep_dive must NOT run."""
    report = run_for("laura_mendez", data_dir=DATA_DIR)
    assert report["overall_score"] < 5.5
    assert report["follow_up_questions"] == []


# ----------------------------------------------------------------------
# Backend selection — mock is the default and never needs an API key
# ----------------------------------------------------------------------


def test_default_backend_is_mock():
    from src.services import LLMClient
    client = LLMClient()
    assert client.backend_name == "mock"

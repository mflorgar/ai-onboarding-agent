"""TypedDict state passed through the LangGraph nodes."""

from __future__ import annotations

from typing import TypedDict

from src.models import (
    CandidateProfile,
    CompetencyScore,
    Document,
    DocumentFinding,
    OnboardingReport,
    RedFlag,
)


class OnboardingState(TypedDict, total=False):
    candidate: CandidateProfile
    video_url: str
    transcript: str
    raw_documents: list[dict]              # [{doc_type, filename, raw_url}]
    documents: list[Document]              # con texto extraído
    competencies: list[CompetencyScore]
    document_findings: list[DocumentFinding]
    red_flags: list[RedFlag]
    overall_score: float
    follow_up_questions: list[str]         # poblado solo si pasa por deep_dive
    report: OnboardingReport
    stage: str
    finished: bool

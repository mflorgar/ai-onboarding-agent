"""Typed models for the onboarding review agent."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Recommendation(str, Enum):
    STRONG_HIRE = "strong_hire"
    HIRE = "hire"
    HIRE_WITH_CAVEATS = "hire_with_caveats"
    NO_HIRE = "no_hire"


class DocumentType(str, Enum):
    CV = "cv"
    CERTIFICATE = "certificate"
    ID = "id"
    PORTFOLIO = "portfolio"
    REFERENCE = "reference"
    OTHER = "other"


class CandidateProfile(BaseModel):
    candidate_id: str
    full_name: str
    role_applied: str
    years_experience: Optional[int] = None
    email: Optional[str] = None


class Document(BaseModel):
    doc_type: DocumentType
    filename: str
    content_text: str = ""
    extracted_at: Optional[datetime] = None


class CompetencyScore(BaseModel):
    """Score for one soft- or hard-skill dimension."""

    name: str
    score: float = Field(..., ge=0.0, le=10.0)
    evidence: str = ""
    status: str = "at_expected"  # above_expected | at_expected | below_expected


class DocumentFinding(BaseModel):
    doc_type: DocumentType
    filename: str
    is_consistent: bool
    notes: str = ""


class RedFlag(BaseModel):
    severity: str  # low | medium | high
    title: str
    detail: str


class OnboardingReport(BaseModel):
    """Final artefact produced by the graph."""

    candidate: CandidateProfile
    transcript_snippet: str
    competencies: list[CompetencyScore]
    document_findings: list[DocumentFinding]
    red_flags: list[RedFlag]
    overall_score: float = Field(..., ge=0.0, le=10.0)
    recommendation: Recommendation
    summary: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)

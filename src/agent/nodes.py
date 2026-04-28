"""LangGraph nodes for the onboarding review pipeline.

Each node is a pure-ish function that takes the state, calls a service,
and returns the new state. Services are captured in closure by
``NodeFactory`` so the state stays serializable (no clients inside).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.models import OnboardingReport, Recommendation
from src.services import DocumentExtractorClient, LLMClient, TranscriberClient

from .states import OnboardingState


@dataclass
class NodeFactory:
    transcriber: TranscriberClient
    extractor: DocumentExtractorClient
    llm: LLMClient

    # ---- nodes --------------------------------------------------------

    def ingest(self, state: OnboardingState) -> OnboardingState:
        # Valida que tenemos lo mínimo: candidate + video_url + raw_documents
        candidate = state.get("candidate")
        if not candidate:
            raise ValueError("ingest: missing candidate profile")
        return {**state, "stage": "transcribe"}

    def transcribe(self, state: OnboardingState) -> OnboardingState:
        candidate = state["candidate"]
        transcript = self.transcriber.transcribe(
            candidate.candidate_id, state.get("video_url", "")
        )
        return {**state, "transcript": transcript, "stage": "extract_documents"}

    def extract_documents(self, state: OnboardingState) -> OnboardingState:
        candidate = state["candidate"]
        documents = self.extractor.extract(
            candidate.candidate_id, state.get("raw_documents", [])
        )
        return {**state, "documents": documents, "stage": "analyze_answers"}

    def analyze_answers(self, state: OnboardingState) -> OnboardingState:
        candidate = state["candidate"]
        competencies = self.llm.analyze_transcript(
            state.get("transcript", ""), candidate.role_applied
        )
        return {**state, "competencies": competencies, "stage": "verify_documents"}

    def verify_documents(self, state: OnboardingState) -> OnboardingState:
        candidate = state["candidate"]
        findings, flags = self.llm.verify_documents(
            state.get("documents", []),
            candidate.role_applied,
            state.get("transcript", ""),
        )
        return {
            **state,
            "document_findings": findings,
            "red_flags": flags,
            "stage": "score_candidate",
        }

    def score_candidate(self, state: OnboardingState) -> OnboardingState:
        competencies = state.get("competencies", [])
        flags = state.get("red_flags", [])
        base = sum(c.score for c in competencies) / max(1, len(competencies))
        # red flags penalize slightly
        penalty = sum({"low": 0.2, "medium": 0.6, "high": 1.4}.get(f.severity, 0.4) for f in flags)
        overall = round(max(0.0, min(10.0, base - penalty)), 1)
        return {**state, "overall_score": overall, "stage": "score_candidate"}

    def deep_dive(self, state: OnboardingState) -> OnboardingState:
        """Borderline candidates only. Generates follow-up questions
        targeting the weakest competencies and the top red flag."""
        candidate = state["candidate"]
        questions = self.llm.propose_followups(
            candidate.full_name,
            candidate.role_applied,
            state.get("competencies", []),
            state.get("red_flags", []),
        )
        return {**state, "follow_up_questions": questions, "stage": "generate_report"}

    def generate_report(self, state: OnboardingState) -> OnboardingState:
        candidate = state["candidate"]
        overall = state.get("overall_score", 0.0)
        red_flags = state.get("red_flags", [])

        recommendation = _recommendation_for(overall, red_flags)
        summary = self.llm.summarize(
            candidate.full_name,
            candidate.role_applied,
            state.get("competencies", []),
            red_flags,
            overall,
        )
        report = OnboardingReport(
            candidate=candidate,
            transcript_snippet=state.get("transcript", "")[:280],
            competencies=state.get("competencies", []),
            document_findings=state.get("document_findings", []),
            red_flags=red_flags,
            overall_score=overall,
            recommendation=recommendation,
            summary=summary,
            follow_up_questions=state.get("follow_up_questions", []),
        )
        return {**state, "report": report, "stage": "done", "finished": True}


def route_after_score(state: OnboardingState) -> str:
    """Conditional edge: borderline scores get a deep_dive pass."""
    score = state.get("overall_score", 0.0)
    if 5.5 <= score <= 6.5:
        return "deep_dive"
    return "generate_report"


def _recommendation_for(score: float, red_flags) -> Recommendation:
    has_high_flag = any(f.severity == "high" for f in red_flags)
    has_medium_flag = any(f.severity == "medium" for f in red_flags)

    if has_high_flag:
        return Recommendation.NO_HIRE
    if score >= 8.0:
        return Recommendation.STRONG_HIRE
    if score >= 6.5 and not has_medium_flag:
        return Recommendation.HIRE
    if score >= 5.5:
        return Recommendation.HIRE_WITH_CAVEATS
    return Recommendation.NO_HIRE

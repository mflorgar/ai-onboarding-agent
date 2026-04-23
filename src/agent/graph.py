"""LangGraph wiring for the onboarding review pipeline.

Linear flow:

    ingest → transcribe → extract_documents → analyze_answers
           → verify_documents → score_candidate → generate_report → END

No branching for the MVP. Future extensions (e.g. re-interview loop if
the score is borderline, async human-in-the-loop step) slot as
conditional edges from score_candidate.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.services import DocumentExtractorClient, LLMClient, TranscriberClient

from .nodes import NodeFactory
from .states import OnboardingState


def build_graph(
    transcriber: TranscriberClient | None = None,
    extractor: DocumentExtractorClient | None = None,
    llm: LLMClient | None = None,
):
    nodes = NodeFactory(
        transcriber=transcriber or TranscriberClient(),
        extractor=extractor or DocumentExtractorClient(),
        llm=llm or LLMClient(),
    )

    graph = StateGraph(OnboardingState)
    graph.add_node("ingest", nodes.ingest)
    graph.add_node("transcribe", nodes.transcribe)
    graph.add_node("extract_documents", nodes.extract_documents)
    graph.add_node("analyze_answers", nodes.analyze_answers)
    graph.add_node("verify_documents", nodes.verify_documents)
    graph.add_node("score_candidate", nodes.score_candidate)
    graph.add_node("generate_report", nodes.generate_report)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "transcribe")
    graph.add_edge("transcribe", "extract_documents")
    graph.add_edge("extract_documents", "analyze_answers")
    graph.add_edge("analyze_answers", "verify_documents")
    graph.add_edge("verify_documents", "score_candidate")
    graph.add_edge("score_candidate", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()

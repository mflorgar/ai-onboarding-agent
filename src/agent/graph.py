"""LangGraph wiring for the onboarding review pipeline.

Flow:

    ingest → transcribe → extract_documents → analyze_answers
           → verify_documents → score_candidate
                              ↘ (borderline 5.5–6.5)
                                 deep_dive → generate_report → END
                              ↘ (otherwise)
                                 generate_report → END

The conditional edge from ``score_candidate`` is the part that justifies
LangGraph over a flat script: borderline candidates trigger a follow-up
question generation pass before the final report is written.

Optional human-in-the-loop: ``build_graph(human_in_the_loop=True)``
compiles the graph with a checkpointer and ``interrupt_before=["generate_report"]``
so a recruiter can review competencies and flags before the agent commits
to a recommendation. Resume by re-invoking with the same thread id.
"""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from src.services import DocumentExtractorClient, LLMClient, TranscriberClient

from .nodes import NodeFactory, route_after_score
from .states import OnboardingState


def build_graph(
    transcriber: TranscriberClient | None = None,
    extractor: DocumentExtractorClient | None = None,
    llm: LLMClient | None = None,
    human_in_the_loop: bool = False,
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
    graph.add_node("deep_dive", nodes.deep_dive)
    graph.add_node("generate_report", nodes.generate_report)

    graph.set_entry_point("ingest")
    graph.add_edge("ingest", "transcribe")
    graph.add_edge("transcribe", "extract_documents")
    graph.add_edge("extract_documents", "analyze_answers")
    graph.add_edge("analyze_answers", "verify_documents")
    graph.add_edge("verify_documents", "score_candidate")
    graph.add_conditional_edges(
        "score_candidate",
        route_after_score,
        {"deep_dive": "deep_dive", "generate_report": "generate_report"},
    )
    graph.add_edge("deep_dive", "generate_report")
    graph.add_edge("generate_report", END)

    if human_in_the_loop:
        from langgraph.checkpoint.memory import MemorySaver
        return graph.compile(
            checkpointer=MemorySaver(),
            interrupt_before=["generate_report"],
        )
    return graph.compile()
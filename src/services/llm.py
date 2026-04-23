"""LLM service.

Deterministic mock that classifies candidate quality using keyword
heuristics over the transcript and documents. Good enough to exercise
the graph end-to-end and produce realistic-looking reports.

For real usage, swap to Gemini / Anthropic / OpenAI by implementing the
same three methods below.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from src.models import CompetencyScore, DocumentFinding, Document, RedFlag


# Señales que usa el mock. No son determinísticas de "la verdad" sino
# heurísticas que simulan el juicio de un LLM real.
STRONG_SIGNALS = [
    "specifically", "we shipped", "reduced", "increased", "led",
    "arquitectura", "migramos", "reduje", "ahorré", "entregamos",
    "métrica", "impacto", "stakeholders",
]
WEAK_SIGNALS = [
    "i guess", "maybe", "not sure", "creo que",
    "no recuerdo", "quizás", "depende",
]
RED_FLAG_SIGNALS = [
    "gap", "fired", "despidieron", "no termin", "dejé sin acabar",
    "mentí", "no es mi culpa",
]


@dataclass
class LLMClient:
    """Quality-judge LLM with keyword heuristics.

    Methods:
    - analyze_transcript: extrae competencias del transcript
    - verify_documents: compara cada doc con el perfil
    - summarize: genera un párrafo de resumen ejecutivo
    """

    provider: str = ""

    def __post_init__(self) -> None:
        self.provider = self.provider or os.getenv("LLM_PROVIDER", "mock")

    # ---- public API --------------------------------------------------

    def analyze_transcript(self, transcript: str, role: str) -> list[CompetencyScore]:
        """Score 6 competencies 0-10 based on keyword signals."""
        t = transcript.lower()
        strong = sum(1 for s in STRONG_SIGNALS if s in t)
        weak = sum(1 for s in WEAK_SIGNALS if s in t)
        length = len(transcript.split())

        # base score derived from signal counts and length
        base = 5.0 + min(strong * 0.7, 3.5) - min(weak * 0.6, 2.5)
        if length < 80:
            base -= 1.5
        elif length > 400:
            base += 0.5
        base = max(0.0, min(10.0, base))

        # small deterministic variation per competency
        def _score(offset: float) -> float:
            return round(max(0.0, min(10.0, base + offset)), 1)

        def _status(score: float) -> str:
            if score >= 7.5:
                return "above_expected"
            if score >= 5.0:
                return "at_expected"
            return "below_expected"

        def _evidence(default: str) -> str:
            # pick the first sentence with a strong signal, if any
            for s in STRONG_SIGNALS:
                idx = transcript.lower().find(s)
                if idx >= 0:
                    start = max(0, idx - 30)
                    end = min(len(transcript), idx + 60)
                    return "…" + transcript[start:end].strip() + "…"
            return default

        comps = [
            CompetencyScore(name="Comunicación",        score=_score(0.3),  evidence=_evidence("sin evidencia clara")),
            CompetencyScore(name="Resolución de problemas", score=_score(-0.1), evidence=_evidence("sin evidencia clara")),
            CompetencyScore(name="Experiencia técnica",  score=_score(0.5),  evidence=_evidence("sin evidencia clara")),
            CompetencyScore(name="Fit cultural",        score=_score(-0.3), evidence=_evidence("sin evidencia clara")),
            CompetencyScore(name="Motivación",          score=_score(0.1),  evidence=_evidence("sin evidencia clara")),
            CompetencyScore(name="Liderazgo",           score=_score(-0.5), evidence=_evidence("sin evidencia clara")),
        ]
        for c in comps:
            c.status = _status(c.score)
        return comps

    def verify_documents(
        self, documents: list[Document], role: str, transcript: str
    ) -> tuple[list[DocumentFinding], list[RedFlag]]:
        findings: list[DocumentFinding] = []
        flags: list[RedFlag] = []

        for doc in documents:
            text = doc.content_text.lower()
            consistent = True
            notes = "Consistente con el perfil declarado."

            if doc.doc_type.value == "cv":
                # ejemplos de chequeos que haría un LLM real
                if "gap" in text or "sin empleo" in text:
                    consistent = False
                    notes = "Gap de empleo sin contexto en el CV."
                    flags.append(RedFlag(
                        severity="medium",
                        title="Gap de empleo no explicado",
                        detail="El CV muestra un período sin empleo sin justificación en el transcript.",
                    ))
                if "mentí" in text or "inconsisten" in text:
                    consistent = False
                    notes = "Inconsistencia entre CV y transcript."
                    flags.append(RedFlag(
                        severity="high",
                        title="Inconsistencia CV vs entrevista",
                        detail="Hechos declarados en el CV no se corresponden con lo dicho en la entrevista.",
                    ))

            if doc.doc_type.value == "certificate":
                if "expirado" in text or "caduc" in text:
                    consistent = False
                    notes = "La certificación aparece caducada."
                    flags.append(RedFlag(
                        severity="low",
                        title="Certificación caducada",
                        detail=f"{doc.filename} reporta estar caducada.",
                    ))

            findings.append(DocumentFinding(
                doc_type=doc.doc_type,
                filename=doc.filename,
                is_consistent=consistent,
                notes=notes,
            ))

        # Red flags from transcript itself
        for s in RED_FLAG_SIGNALS:
            if s in transcript.lower():
                flags.append(RedFlag(
                    severity="medium",
                    title="Señal de alerta en la entrevista",
                    detail=f"El transcript menciona '{s}', vale la pena profundizar.",
                ))
                break

        return findings, flags

    def summarize(
        self,
        candidate_name: str,
        role: str,
        competencies: list[CompetencyScore],
        red_flags: list[RedFlag],
        overall: float,
    ) -> str:
        avg_competency = sum(c.score for c in competencies) / max(1, len(competencies))
        strong = [c.name for c in competencies if c.score >= 7.5]
        weak = [c.name for c in competencies if c.score < 5.0]

        parts = [
            f"{candidate_name} aplica al rol de {role} con una puntuación global de {overall:.1f}/10.",
        ]
        if strong:
            parts.append(f"Destaca en: {', '.join(strong)}.")
        if weak:
            parts.append(f"Áreas débiles: {', '.join(weak)}.")
        if red_flags:
            parts.append(f"Se identificaron {len(red_flags)} red flag(s) a revisar en siguiente ronda.")
        else:
            parts.append("No se detectaron red flags.")
        return " ".join(parts)

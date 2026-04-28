"""LLM service.

Two interchangeable backends, picked by the ``LLM_PROVIDER`` env var
(or by passing ``LLMClient(provider=...)`` explicitly):

- ``mock`` (default) — deterministic keyword-based heuristics. No API
  key, no network, no flakiness. Lets the graph and tests run zero-config
  and powers the demo's offline fallback.
- ``gemini`` — real Google Gemini call using **structured outputs**
  (``response_schema``). Returns typed pydantic objects, no JSON parsing
  in user code. Requires ``GEMINI_API_KEY``.

Both backends expose the same surface:

    analyze_transcript(transcript, role) -> list[CompetencyScore]
    verify_documents(docs, role, transcript) -> (findings, red_flags)
    summarize(name, role, comps, flags, overall) -> str
    propose_followups(name, role, comps, flags) -> list[str]
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

from src.models import CompetencyScore, Document, DocumentFinding, RedFlag


# ---------------------------------------------------------------------------
# Heuristics shared by mock backend
# ---------------------------------------------------------------------------

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

COMPETENCY_NAMES = [
    ("Comunicación", 0.3),
    ("Resolución de problemas", -0.1),
    ("Experiencia técnica", 0.5),
    ("Fit cultural", -0.3),
    ("Motivación", 0.1),
    ("Liderazgo", -0.5),
]


# ---------------------------------------------------------------------------
# Pydantic schemas for Gemini structured outputs
# ---------------------------------------------------------------------------


class _CompetencyOut(BaseModel):
    name: str
    score: float
    evidence: str
    status: str  # above_expected | at_expected | below_expected


class _CompetenciesOut(BaseModel):
    competencies: list[_CompetencyOut]


class _DocFindingOut(BaseModel):
    filename: str
    is_consistent: bool
    notes: str


class _RedFlagOut(BaseModel):
    severity: str  # low | medium | high
    title: str
    detail: str


class _VerifyOut(BaseModel):
    findings: list[_DocFindingOut]
    red_flags: list[_RedFlagOut]


class _FollowupsOut(BaseModel):
    questions: list[str]


# ---------------------------------------------------------------------------
# Backend protocol
# ---------------------------------------------------------------------------


class _Backend(Protocol):
    name: str
    def analyze_transcript(self, transcript: str, role: str) -> list[CompetencyScore]: ...
    def verify_documents(
        self, documents: list[Document], role: str, transcript: str
    ) -> tuple[list[DocumentFinding], list[RedFlag]]: ...
    def summarize(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag], overall: float,
    ) -> str: ...
    def propose_followups(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag],
    ) -> list[str]: ...


# ---------------------------------------------------------------------------
# Mock backend (deterministic, offline)
# ---------------------------------------------------------------------------


class _MockBackend:
    name = "mock"

    def analyze_transcript(self, transcript: str, role: str) -> list[CompetencyScore]:
        t = transcript.lower()
        strong = sum(1 for s in STRONG_SIGNALS if s in t)
        weak = sum(1 for s in WEAK_SIGNALS if s in t)
        length = len(transcript.split())

        base = 5.0 + min(strong * 0.7, 3.5) - min(weak * 0.6, 2.5)
        if length < 80:
            base -= 1.5
        elif length > 400:
            base += 0.5
        base = max(0.0, min(10.0, base))

        def _evidence(default: str) -> str:
            for s in STRONG_SIGNALS:
                idx = transcript.lower().find(s)
                if idx >= 0:
                    start = max(0, idx - 30)
                    end = min(len(transcript), idx + 60)
                    return "…" + transcript[start:end].strip() + "…"
            return default

        def _status(score: float) -> str:
            if score >= 7.5:
                return "above_expected"
            if score >= 5.0:
                return "at_expected"
            return "below_expected"

        comps: list[CompetencyScore] = []
        for name, offset in COMPETENCY_NAMES:
            score = round(max(0.0, min(10.0, base + offset)), 1)
            comps.append(CompetencyScore(
                name=name, score=score,
                evidence=_evidence("sin evidencia clara"),
                status=_status(score),
            ))
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
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag], overall: float,
    ) -> str:
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

    def propose_followups(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag],
    ) -> list[str]:
        weak = sorted(competencies, key=lambda c: c.score)[:2]
        questions: list[str] = []
        for c in weak:
            questions.append(
                f"¿Puedes contarnos un caso concreto donde hayas demostrado "
                f"{c.name.lower()}, idealmente con métricas de impacto?"
            )
        if red_flags:
            top = red_flags[0]
            questions.append(
                f"Sobre '{top.title}': ¿qué contexto adicional aportarías y "
                f"qué aprendiste de esa situación?"
            )
        return questions[:3]


# ---------------------------------------------------------------------------
# Gemini backend (real LLM, structured outputs)
# ---------------------------------------------------------------------------


class _GeminiBackend:
    name = "gemini"

    def __init__(self, model: str = "gemini-2.5-flash") -> None:
        try:
            from google import genai  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Gemini provider requested but `google-genai` is not "
                "installed. Run `pip install google-genai`."
            ) from e
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Gemini provider requested but neither GEMINI_API_KEY nor "
                "GOOGLE_API_KEY is set."
            )
        self._genai = genai
        self._client = genai.Client(api_key=api_key)
        self._model = model

    def _generate_structured(self, prompt: str, schema, temperature: float = 0.2):
        from google.genai import types  # type: ignore
        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
                temperature=temperature,
            ),
        )
        # `parsed` is the pydantic instance when response_schema is set
        return resp.parsed

    def _generate_text(self, prompt: str, temperature: float = 0.3) -> str:
        from google.genai import types  # type: ignore
        resp = self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=temperature),
        )
        return (resp.text or "").strip()

    # ---- public API --------------------------------------------------

    def analyze_transcript(self, transcript: str, role: str) -> list[CompetencyScore]:
        prompt = (
            f"Eres un hiring manager senior revisando la grabación transcrita "
            f"de una entrevista asíncrona para el rol '{role}'. "
            f"Puntúa al candidato en estas seis competencias en escala 0-10: "
            f"Comunicación, Resolución de problemas, Experiencia técnica, "
            f"Fit cultural, Motivación, Liderazgo. "
            f"Para cada una entrega evidencia textual citada del transcript "
            f"(máx 1 frase) y un status ∈ {{'above_expected','at_expected','below_expected'}}. "
            f"Sé estricto: respuestas vagas o sin métricas deben puntuar por "
            f"debajo de 5. Responde en español.\n\n"
            f"TRANSCRIPT:\n{transcript}"
        )
        out: _CompetenciesOut = self._generate_structured(prompt, _CompetenciesOut)
        return [
            CompetencyScore(
                name=c.name,
                score=max(0.0, min(10.0, c.score)),
                evidence=c.evidence,
                status=c.status if c.status in {"above_expected", "at_expected", "below_expected"} else "at_expected",
            )
            for c in (out.competencies if out else [])
        ]

    def verify_documents(
        self, documents: list[Document], role: str, transcript: str
    ) -> tuple[list[DocumentFinding], list[RedFlag]]:
        if not documents:
            return [], []
        doc_blob = "\n\n".join(
            f"--- DOCUMENT filename={d.filename} type={d.doc_type.value} ---\n{d.content_text}"
            for d in documents
        )
        prompt = (
            f"Estás revisando los documentos de un candidato al rol '{role}'. "
            f"Para cada documento, decide si su contenido es consistente con "
            f"el transcript de la entrevista. Identifica también red flags: "
            f"gaps de empleo, certificaciones caducadas, inconsistencias entre "
            f"CV y transcript, falta de responsabilidad, mentiras admitidas. "
            f"La severidad debe ser 'low' | 'medium' | 'high'. "
            f"Usa exactamente los filenames recibidos.\n\n"
            f"TRANSCRIPT:\n{transcript}\n\nDOCUMENTOS:\n{doc_blob}"
        )
        out: _VerifyOut = self._generate_structured(prompt, _VerifyOut)
        doc_type_by_name = {d.filename: d.doc_type for d in documents}
        findings: list[DocumentFinding] = []
        for f in (out.findings if out else []):
            if f.filename not in doc_type_by_name:
                continue
            findings.append(DocumentFinding(
                doc_type=doc_type_by_name[f.filename],
                filename=f.filename,
                is_consistent=f.is_consistent,
                notes=f.notes,
            ))
        flags = [
            RedFlag(
                severity=r.severity if r.severity in {"low", "medium", "high"} else "medium",
                title=r.title,
                detail=r.detail,
            )
            for r in (out.red_flags if out else [])
        ]
        return findings, flags

    def summarize(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag], overall: float,
    ) -> str:
        comp_blob = "\n".join(f"- {c.name}: {c.score}/10 ({c.status})" for c in competencies)
        flag_blob = "\n".join(f"- [{f.severity}] {f.title}: {f.detail}" for f in red_flags) or "Ninguno"
        prompt = (
            f"Escribe un resumen ejecutivo en español (máx. 5 frases) sobre "
            f"{candidate_name}, candidato a '{role}'. Score global: {overall}/10.\n\n"
            f"COMPETENCIAS:\n{comp_blob}\n\nRED FLAGS:\n{flag_blob}\n\n"
            f"Destaca fortalezas, debilidades y propón un siguiente paso claro."
        )
        return self._generate_text(prompt, temperature=0.3)

    def propose_followups(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag],
    ) -> list[str]:
        weak = [c.name for c in competencies if c.score < 6.0]
        flag_blob = "\n".join(f"- {f.title}" for f in red_flags) or "Ninguno"
        prompt = (
            f"El candidato {candidate_name} (rol '{role}') tiene un score "
            f"borderline. Áreas débiles: {', '.join(weak) or 'ninguna marcada'}. "
            f"Red flags:\n{flag_blob}\n\n"
            f"Propón 2-3 preguntas concretas en español para una segunda ronda "
            f"diseñadas a desambiguar las dudas. Devuelve sólo las preguntas."
        )
        out: _FollowupsOut = self._generate_structured(prompt, _FollowupsOut, temperature=0.4)
        return list(out.questions[:3]) if out else []


# ---------------------------------------------------------------------------
# Public client
# ---------------------------------------------------------------------------


@dataclass
class LLMClient:
    """Front-facing LLM client. Selects backend at construction time.

    >>> LLMClient()                        # mock by default
    >>> LLMClient(provider="gemini")       # real Gemini call (needs API key)
    >>> os.environ["LLM_PROVIDER"]="gemini"; LLMClient()  # via env var
    """

    provider: str = ""

    def __post_init__(self) -> None:
        self.provider = self.provider or os.getenv("LLM_PROVIDER", "mock")
        if self.provider == "gemini":
            self._backend: _Backend = _GeminiBackend()
        else:
            self._backend = _MockBackend()
            self.provider = self._backend.name

    @property
    def backend_name(self) -> str:
        return self._backend.name

    def analyze_transcript(self, transcript: str, role: str) -> list[CompetencyScore]:
        return self._backend.analyze_transcript(transcript, role)

    def verify_documents(
        self, documents: list[Document], role: str, transcript: str
    ) -> tuple[list[DocumentFinding], list[RedFlag]]:
        return self._backend.verify_documents(documents, role, transcript)

    def summarize(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag], overall: float,
    ) -> str:
        return self._backend.summarize(candidate_name, role, competencies, red_flags, overall)

    def propose_followups(
        self, candidate_name: str, role: str,
        competencies: list[CompetencyScore], red_flags: list[RedFlag],
    ) -> list[str]:
        return self._backend.propose_followups(candidate_name, role, competencies, red_flags)
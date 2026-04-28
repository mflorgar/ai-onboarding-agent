"""Vercel serverless entrypoint that runs the LangGraph pipeline.

Endpoints
---------
``GET  /api/analyze`` — health probe. Returns ``{"backend": "gemini"|"mock"}``
so the demo can show a "Live · Powered by Gemini" badge when the API key
is configured server-side.

``POST /api/analyze`` — run the agent.

Request body (JSON):

    {
      "candidate_id": "ana_garcia" | "marco_silva" | "laura_mendez" | null,
      "candidate":   { "candidate_id": str, "full_name": str, "role_applied": str, ... }, // when custom
      "transcript":  str,        // optional override / required for custom
      "documents":   [           // optional override / required for custom
        { "doc_type": "cv"|"certificate"|..., "filename": str, "content_text": str }
      ]
    }

If ``candidate_id`` matches a preset, the transcript and documents are
loaded from ``data/candidates/<id>/`` on the server (no need to send them
over the wire). For a Custom candidate, the body must include
``candidate``, ``transcript`` and (optionally) ``documents``.

Response:

    {
      "backend": "gemini" | "mock",
      "latency_ms": int,
      "report": OnboardingReport (model_dump),
      "deep_dive_triggered": bool   // true when the borderline branch fired
    }
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Vercel mounts the function file at api/analyze.py. The repo root is one
# level up — add it to sys.path so we can import the LangGraph pipeline.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent.graph import build_graph  # noqa: E402
from src.models import (  # noqa: E402
    CandidateProfile,
    Document,
    DocumentType,
)
from src.services import LLMClient  # noqa: E402


PRESET_PROFILES = {
    "ana_garcia":   {"full_name": "Ana García",   "role_applied": "Senior Data Engineer", "years_experience": 7, "email": "ana.garcia@example.com"},
    "marco_silva":  {"full_name": "Marco Silva",  "role_applied": "Marketing Manager",    "years_experience": 5, "email": "marco.silva@example.com"},
    "laura_mendez": {"full_name": "Laura Méndez", "role_applied": "Product Designer",     "years_experience": 3, "email": "laura.mendez@example.com"},
}

DATA_DIR = ROOT / "data" / "candidates"


# ---------------------------------------------------------------------------
# Inline service implementations (transcribe / extract are no-ops here:
# the request body provides the data already)
# ---------------------------------------------------------------------------


class _InlineTranscriber:
    def __init__(self, transcript: str) -> None:
        self._t = transcript

    def transcribe(self, candidate_id: str, video_url: str = "") -> str:  # noqa: ARG002
        return self._t


class _InlineExtractor:
    def __init__(self, docs: list[dict]) -> None:
        self._docs = docs

    def extract(self, candidate_id: str, raw_documents: list[dict]) -> list[Document]:  # noqa: ARG002
        out: list[Document] = []
        for d in self._docs:
            try:
                doc_type = DocumentType(d.get("doc_type", "other"))
            except ValueError:
                doc_type = DocumentType.OTHER
            out.append(Document(
                doc_type=doc_type,
                filename=d.get("filename", "doc"),
                content_text=d.get("content_text", ""),
                extracted_at=datetime.utcnow(),
            ))
        return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_doc_type(filename: str) -> str:
    n = filename.lower()
    if "cv" in n or "resume" in n:
        return "cv"
    if "cert" in n:
        return "certificate"
    if "id" in n or "passport" in n:
        return "id"
    if "portfolio" in n:
        return "portfolio"
    if "ref" in n:
        return "reference"
    return "other"


def _load_preset(candidate_id: str) -> tuple[CandidateProfile, str, list[dict]]:
    """Load a preset candidate from the bundled data/candidates/<id>/ folder."""
    folder = DATA_DIR / candidate_id
    profile_seed = PRESET_PROFILES[candidate_id] | {"candidate_id": candidate_id}
    candidate = CandidateProfile(**profile_seed)

    transcript_path = folder / "transcript.txt"
    transcript = transcript_path.read_text(encoding="utf-8").strip() if transcript_path.exists() else ""

    documents: list[dict] = []
    if folder.exists():
        for path in sorted(folder.iterdir()):
            if path.name in {"transcript.txt", "profile.json"}:
                continue
            if path.suffix.lower() != ".txt":
                continue
            documents.append({
                "doc_type": _resolve_doc_type(path.name),
                "filename": path.name,
                "content_text": path.read_text(encoding="utf-8").strip(),
            })
    return candidate, transcript, documents


def _pick_provider() -> str:
    """Prefer Gemini if a key is configured; fall back to mock otherwise."""
    if os.getenv("LLM_PROVIDER"):
        return os.environ["LLM_PROVIDER"]
    if os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"):
        return "gemini"
    return "mock"


def _build_llm() -> LLMClient:
    provider = _pick_provider()
    try:
        return LLMClient(provider=provider)
    except RuntimeError:
        # Gemini init failed (e.g. dep not installed) — fall back gracefully.
        return LLMClient(provider="mock")


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def run_analysis(payload: dict) -> dict:
    candidate_id = payload.get("candidate_id")

    if candidate_id and candidate_id in PRESET_PROFILES and not payload.get("transcript"):
        candidate, transcript, documents = _load_preset(candidate_id)
    else:
        cand_data = payload.get("candidate") or {}
        if not cand_data.get("candidate_id"):
            cand_data["candidate_id"] = candidate_id or "custom"
        candidate = CandidateProfile(**cand_data)
        transcript = payload.get("transcript", "")
        documents = payload.get("documents", [])

    llm = _build_llm()
    transcriber = _InlineTranscriber(transcript)
    extractor = _InlineExtractor(documents)

    graph = build_graph(transcriber=transcriber, extractor=extractor, llm=llm)
    final_state = graph.invoke({
        "candidate": candidate,
        "video_url": payload.get("video_url", ""),
        "raw_documents": [
            {"doc_type": d.get("doc_type", "other"), "filename": d.get("filename", "")}
            for d in documents
        ],
    })

    report = final_state["report"]
    return {
        "backend": llm.backend_name,
        "report": report.model_dump(mode="json"),
        "deep_dive_triggered": bool(final_state.get("follow_up_questions")),
    }


# ---------------------------------------------------------------------------
# Vercel HTTP handler
# ---------------------------------------------------------------------------


class handler(BaseHTTPRequestHandler):
    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, status: int, body: dict) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(body, ensure_ascii=False, default=str).encode("utf-8"))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        provider = _pick_provider()
        # Surface whether google-genai is actually importable in this env,
        # so the demo can downgrade to mock proactively if needed.
        gemini_ok = False
        if provider == "gemini":
            try:
                import google.genai  # type: ignore  # noqa: F401
                gemini_ok = True
            except ImportError:
                gemini_ok = False
        effective = "gemini" if (provider == "gemini" and gemini_ok) else "mock"
        self._json(200, {"status": "ok", "backend": effective, "presets": list(PRESET_PROFILES)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as e:
            self._json(400, {"error": "invalid_json", "detail": str(e)})
            return

        t0 = time.time()
        try:
            result = run_analysis(payload)
        except Exception as e:
            self._json(500, {"error": type(e).__name__, "detail": str(e)})
            return
        result["latency_ms"] = int((time.time() - t0) * 1000)
        self._json(200, result)
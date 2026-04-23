"""Video transcription service.

Thin interface with a deterministic mock so the graph runs without any
external API. Swap the mock for a real backend (AssemblyAI, Whisper API,
Hireflix webhook, etc.) by implementing the same interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class TranscriberClient:
    """Returns the text transcript for a candidate's recorded video.

    The mock loads from ``data/candidates/<candidate_id>/transcript.txt``
    so tests and the demo runner can exercise the full graph without
    hitting a real transcription provider.
    """

    data_dir: Path = Path("data/candidates")

    def transcribe(self, candidate_id: str, video_url: str = "") -> str:
        path = self.data_dir / candidate_id / "transcript.txt"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        # fallback para cuando no hay fixture
        return f"[no transcript available for {candidate_id}]"

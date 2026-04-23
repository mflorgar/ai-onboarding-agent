"""Document text extraction service.

Mock implementation that reads `.txt` fixtures from the data directory.
In production this would plug into OCR (Azure Form Recognizer, AWS
Textract) or direct PDF/DOCX parsing (pypdf, python-docx) depending on
the file type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from src.models import Document, DocumentType


@dataclass
class DocumentExtractorClient:
    data_dir: Path = Path("data/candidates")

    def extract(self, candidate_id: str, raw_documents: list[dict]) -> list[Document]:
        out: list[Document] = []
        for meta in raw_documents:
            filename = meta.get("filename", "")
            doc_type = DocumentType(meta.get("doc_type", "other"))
            path = self.data_dir / candidate_id / filename
            text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            out.append(Document(
                doc_type=doc_type,
                filename=filename,
                content_text=text,
                extracted_at=datetime.utcnow(),
            ))
        return out

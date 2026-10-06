"""Document ingestion: text per page. Scanned PDFs yield empty pages and are flagged downstream."""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader


def extract_pages(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        return [(p.extract_text() or "").strip() for p in reader.pages]
    if suffix in {".txt", ".md"}:
        text = path.read_text(encoding="utf-8", errors="replace")
        # Form feed separates pages in plain-text fixtures.
        return [p.strip() for p in text.split("\f")]
    raise ValueError(f"Unsupported file type: {suffix} (PDF or TXT expected)")

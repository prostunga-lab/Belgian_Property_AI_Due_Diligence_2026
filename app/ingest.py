"""Document ingestion: text per page, with OCR fallback for scanned pages and images."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from . import config, ocr


@dataclass
class Ingested:
    pages: list[str]
    ocr_pages: list[dict] = field(default_factory=list)  # [{"page": n, "confidence": c}]
    warnings: list[str] = field(default_factory=list)  # codes, translated at display time (see render.warning_text)


def supported_extensions() -> set[str]:
    return {".pdf", ".txt", ".md"} | ocr.IMAGE_EXT


def extract_pages(path: Path) -> Ingested:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        # Form feed separates pages in plain-text fixtures.
        text = path.read_text(encoding="utf-8", errors="replace")
        return Ingested([p.strip() for p in text.split("\f")])
    if suffix in ocr.IMAGE_EXT:
        return _ocr_image(path)
    if suffix == ".pdf":
        return _pdf(path)
    raise ValueError(f"Unsupported file type: {suffix}")


def _ocr_image(path: Path) -> Ingested:
    if not ocr.available():
        return Ingested([""], warnings=["ocr_unavailable_image"])
    page = ocr.ocr_image(path)
    return Ingested([ocr.normalize(page.text)], [{"page": 1, "confidence": page.confidence}])


def _pdf(path: Path) -> Ingested:
    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    out = Ingested(pages)
    scanned = [i for i, t in enumerate(pages) if len(t) < config.OCR_MIN_CHARS]
    if not scanned:
        return out
    if not (ocr.available() and ocr.pdf_renderer_available()):
        out.warnings.append("ocr_unavailable_pdf")
        return out
    for i in scanned:
        try:
            page = ocr.ocr_pdf_page(path, i + 1)
        except Exception as e:  # one bad page must not sink the whole document
            out.warnings.append(f"ocr_failed:{i + 1}")
            continue
        out.pages[i] = ocr.normalize(page.text).strip()
        out.ocr_pages.append({"page": i + 1, "confidence": page.confidence})
    return out

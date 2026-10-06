"""OCR via the Tesseract CLI (+ poppler's pdftoppm for PDF pages). Optional: degrades gracefully when missing."""
from __future__ import annotations

import csv
import io
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import config

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


@dataclass
class OcrPage:
    text: str
    confidence: float  # mean word confidence 0-100


def available() -> bool:
    return config.OCR_ENABLED and shutil.which("tesseract") is not None


def pdf_renderer_available() -> bool:
    return shutil.which("pdftoppm") is not None


def ocr_image(path: Path) -> OcrPage:
    """Run tesseract on one image; rebuild text line by line from the TSV and average word confidences."""
    res = subprocess.run(
        ["tesseract", str(path), "stdout", "-l", config.OCR_LANGS, "--psm", "3", "tsv"],
        capture_output=True, text=True, timeout=config.OCR_TIMEOUT_S, check=True,
    )
    lines: dict[tuple, list[str]] = {}
    confs: list[float] = []
    for row in csv.DictReader(io.StringIO(res.stdout), delimiter="\t", quoting=csv.QUOTE_NONE):
        word = (row.get("text") or "").strip()
        try:
            conf = float(row.get("conf", "-1"))
        except ValueError:
            continue
        if not word or conf < 0:
            continue
        lines.setdefault((row["block_num"], row["par_num"], row["line_num"]), []).append(word)
        confs.append(conf)
    text = "\n".join(" ".join(ws) for ws in lines.values())
    return OcrPage(text, round(sum(confs) / len(confs), 1) if confs else 0.0)


def ocr_pdf_page(pdf: Path, page_number: int) -> OcrPage:
    """page_number is 1-based."""
    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "p"
        subprocess.run(
            ["pdftoppm", "-r", str(config.OCR_DPI), "-f", str(page_number), "-l", str(page_number), "-png", str(pdf), str(prefix)],
            check=True, capture_output=True, timeout=config.OCR_TIMEOUT_S,
        )
        img = next(Path(tmp).glob("p*.png"))
        return ocr_image(img)


def normalize(text: str) -> str:
    """Fix systematic OCR confusions on units that the extractors rely on (m² is often read as m?, m3, m°)."""
    text = re.sub(r"(?<=\d)\s*m\s*[?³°\^]\s*(?!\w)", " m²", text)
    text = re.sub(r"(kWh\s*/\s*m)\s*[?³°\^2]?(?!\w)", r"\1²", text)
    return text

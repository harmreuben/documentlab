"""Tesseract OCR, run locally. Nothing is sent to any outside service.

Tesseract is found on PATH, at the path in the TESSERACT_CMD environment variable, or in its
default Windows install folder. If it can't be found, OCR is reported as unavailable, never
silently skipped.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from functools import lru_cache

MRZ_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
LOW_CONFIDENCE = 60  # words below this are listed for review
_WINDOWS_DEFAULT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"


@dataclass
class OcrResult:
    text: str
    words: list[dict] = field(default_factory=list)   # {"text", "confidence", "box": [x, y, w, h]}
    mean_confidence: float = 0.0
    low_confidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"text": self.text, "mean_confidence": round(self.mean_confidence, 1),
                "word_count": len(self.words), "low_confidence": self.low_confidence[:50]}


def _command() -> str | None:
    configured = os.environ.get("TESSERACT_CMD")
    if configured and os.path.exists(configured):
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    return _WINDOWS_DEFAULT if os.path.exists(_WINDOWS_DEFAULT) else None


@lru_cache(maxsize=1)
def status() -> tuple[bool, str]:
    """(available, version or reason). Cached for the life of the process."""
    try:
        import pytesseract
    except ImportError:
        return False, "pytesseract is not installed."
    command = _command()
    if command is None:
        return False, "Tesseract was not found. Install it, or set TESSERACT_CMD to tesseract.exe."
    pytesseract.pytesseract.tesseract_cmd = command
    try:
        return True, f"Tesseract {pytesseract.get_tesseract_version()}"
    except Exception as exc:  # broken install
        return False, f"Tesseract could not be started: {exc}"


def read_page(image) -> OcrResult:
    import pytesseract

    page = image.convert("L")
    if page.width < 1800:  # Tesseract reads small print better when it is enlarged (tested: fixes I/T confusions)
        factor = min(2.0, 1800 / page.width)
        page = page.resize((int(page.width * factor), int(page.height * factor)))
    data = pytesseract.image_to_data(page, output_type=pytesseract.Output.DICT, config="--psm 3")
    words, lines, last_key = [], [], None
    for i, text in enumerate(data["text"]):
        text = text.strip()
        conf = float(data["conf"][i])
        if not text or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        if key != last_key:
            lines.append([])
            last_key = key
        lines[-1].append(text)
        words.append({"text": text, "confidence": conf,
                      "box": [data["left"][i], data["top"][i], data["width"][i], data["height"][i]]})
    mean = sum(w["confidence"] for w in words) / len(words) if words else 0.0
    low = [w["text"] for w in words if w["confidence"] < LOW_CONFIDENCE]
    return OcrResult("\n".join(" ".join(line) for line in lines), words, mean, low)


def read_mrz_band(image) -> str:
    """OCR the lower part of the page with only MRZ characters allowed. MRZs sit at the bottom
    of passports and ID cards; restricting the characters stops letters like '«' appearing."""
    import pytesseract
    from PIL import ImageOps

    width, height = image.size
    band = image.crop((0, int(height * 0.55), width, height)).convert("L")
    if band.width < 1400:
        factor = 1400 / band.width
        band = band.resize((1400, int(band.height * factor)))
    band = ImageOps.autocontrast(band)
    return pytesseract.image_to_string(band, config=f"--psm 6 -c tessedit_char_whitelist={MRZ_CHARS}")

"""Decodes a freshly generated PNG and compares it with what was meant to be encoded.

Statuses:
    PASS         decoded, correct format, text matches exactly
    FAIL         unreadable, wrong format, or different text
    UNAVAILABLE  the decoder isn't installed, so nothing was checked
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from .symbologies import Symbology

PASS, FAIL, UNAVAILABLE = "PASS", "FAIL", "UNAVAILABLE"


@dataclass
class Verification:
    status: str
    decoded_text: str | None = None
    decoded_format: str | None = None
    detail: str = ""

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def _normalise(symbology: Symbology, text: str) -> str:
    # UPC-A is a subset of EAN-13; decoders report it with a leading 0.
    if symbology.key == "upca" and len(text) == 13 and text.startswith("0"):
        return text[1:]
    return text


def verify(symbology: Symbology, png: bytes, expected: str) -> Verification:
    try:
        import zxingcpp
        from PIL import Image
    except ImportError:
        return Verification(UNAVAILABLE, detail="The barcode decoder (zxing-cpp) is not installed, so this code was not checked.")

    with Image.open(io.BytesIO(png)) as image:
        image.load()
        target = getattr(zxingcpp.BarcodeFormat, symbology.zxing_name)
        results = zxingcpp.read_barcodes(image.convert("RGB"), formats=target)

    if not results:
        return Verification(FAIL, detail=f"The decoder could not read a {symbology.name} in the generated image.")
    result = results[0]
    decoded = _normalise(symbology, result.text)
    found_format = str(result.format)
    if not result.valid:
        return Verification(FAIL, decoded, found_format, "The decoder found the code but reported it as invalid.")
    if decoded != expected:
        return Verification(FAIL, decoded, found_format,
                            "The decoded text differs from the data that was meant to be encoded.")
    return Verification(PASS, decoded, found_format, "Decoded by an independent reader and matched exactly.")

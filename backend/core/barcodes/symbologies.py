"""The barcode formats DocumentLab can generate, and the rules for what each one can hold."""
from __future__ import annotations

from dataclasses import dataclass, field

from .issues import Issues

CODE39_CHARS = set("0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ -.$/+%")


def gs1_check_digit(digits: str) -> str:
    """GS1 modulo-10 check digit, used by EAN-13, EAN-8 and UPC-A.

    Working from the right, digits are weighted 3, 1, 3, 1...; the check digit
    brings the weighted sum up to the next multiple of 10.
    """
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits)))
    return str((10 - total % 10) % 10)


@dataclass(frozen=True)
class Symbology:
    key: str
    name: str
    family: str  # "linear" | "matrix" | "stacked"
    summary: str
    max_length: int
    structured: bool = False  # can carry DocumentLab's structured JSON schemas
    data_lengths: tuple[int, ...] = ()  # fixed-length numeric formats: (without check, with check)
    zxing_name: str = ""
    notes: list[str] = field(default_factory=list)

    def validate(self, text: str, issues: Issues) -> tuple[str, str, str | None]:
        """Check a payload. Returns (render_input, expected_decode, check_digit)."""
        if text == "":
            issues.error("payload", "Enter the data to encode.")
            return "", "", None
        if self.data_lengths:
            return self._validate_gs1(text, issues)
        if len(text) > self.max_length:
            issues.error("payload", f"{self.name} holds at most {self.max_length} characters; this has {len(text)}.")
        if self.key == "code128":
            bad = sorted({c for c in text if not (32 <= ord(c) <= 126)})
            if bad:
                issues.error("payload", f"Code 128 only holds plain keyboard characters. Remove: {_show(bad)}.")
        elif self.key == "code39":
            if text != text.upper() and set(text.upper()) <= CODE39_CHARS:
                issues.warning("payload", "Code 39 has no lowercase letters, so letters will be encoded as capitals.")
                text = text.upper()
            bad = sorted({c for c in text if c not in CODE39_CHARS})
            if bad:
                issues.error("payload", f"Code 39 holds only A-Z, 0-9, space and - . $ / + %. Remove: {_show(bad)}.")
        elif "\x00" in text:
            issues.error("payload", "The data contains a null character, which can't be encoded.")
        return text, text, None

    def _validate_gs1(self, text: str, issues: Issues) -> tuple[str, str, str | None]:
        short, full = self.data_lengths
        if not text.isdigit():
            issues.error("payload", f"{self.name} holds digits only.")
            return text, text, None
        if len(text) == short:
            check = gs1_check_digit(text)
            return text, text + check, check
        if len(text) == full:
            expected = gs1_check_digit(text[:-1])
            if text[-1] != expected:
                issues.error("payload", f"The check digit should be {expected}, not {text[-1]}. "
                                        f"Enter the first {short} digits to have it calculated.")
            return text[:-1], text[:-1] + expected, expected
        issues.error("payload", f"{self.name} needs {short} digits (check digit calculated) or {full} digits; this has {len(text)}.")
        return text, text, None


def _show(chars: list[str]) -> str:
    return " ".join(repr(c) if not c.isprintable() or c == " " else c for c in chars[:10])


SYMBOLOGIES: dict[str, Symbology] = {s.key: s for s in [
    Symbology("qr", "QR Code", "matrix", "Square 2D code for links, text and structured test data.",
              max_length=1000, structured=True, zxing_name="QRCode"),
    Symbology("code128", "Code 128", "linear", "Compact linear code for any keyboard text.",
              max_length=80, zxing_name="Code128"),
    Symbology("code39", "Code 39", "linear", "Older linear code for capitals, digits and a few symbols.",
              max_length=43, zxing_name="Code39Std",
              notes=["Encoded without the optional check character."]),
    Symbology("ean13", "EAN-13", "linear", "13-digit retail product number.",
              max_length=13, data_lengths=(12, 13), zxing_name="EAN13"),
    Symbology("ean8", "EAN-8", "linear", "8-digit retail number for small packs.",
              max_length=8, data_lengths=(7, 8), zxing_name="EAN8"),
    Symbology("upca", "UPC-A", "linear", "12-digit North American retail product number.",
              max_length=12, data_lengths=(11, 12), zxing_name="UPCA"),
    Symbology("pdf417", "PDF417", "stacked",
              "Stacked 2D code for longer structured test data. Neutral DocumentLab schemas only.",
              max_length=1000, structured=True, zxing_name="PDF417"),
]}


def get_symbology(key: str) -> Symbology | None:
    return SYMBOLOGIES.get(key)

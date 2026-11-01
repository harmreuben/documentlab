"""Finds and reads every barcode in an image.

Besides the text, each read records how reliable it was:
  - `valid` / `error`: whether the decoder accepted the symbol (checksum, format)
  - `consistent_reads`: the image is re-read at other scales; a read that only
    succeeds at one scale is fragile and is flagged for review. zxing-cpp gives no
    confidence score, so DocumentLab reports this measured agreement instead of
    inventing a percentage.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# zxing-cpp format names -> DocumentLab format keys. Anything else is read but "not supported".
SUPPORTED = {
    "QR Code": "qr", "Code 128": "code128", "Code 39": "code39", "Code 39 Extended": "code39",
    "EAN-13": "ean13", "EAN-8": "ean8", "UPC-A": "upca", "PDF417": "pdf417",
}
CONSISTENCY_SCALES = (0.75, 1.5)


@dataclass
class Read:
    format_name: str
    format_key: str | None
    text: str
    raw_bytes: bytes
    valid: bool
    error: str
    points: list[tuple[float, float]]
    orientation: float
    inverted: bool
    mirrored: bool
    ec_level: str
    symbology_identifier: str
    content_type: str
    attempts: int = 1
    consistent_reads: int = 1
    alternatives: dict = field(default_factory=dict)  # e.g. the standard Code 39 reading of an "extended" read

    @property
    def supported(self) -> bool:
        return self.format_key is not None


def decoder_version() -> str:
    from importlib.metadata import PackageNotFoundError, version
    try:
        return f"zxing-cpp {version('zxing-cpp')}"
    except PackageNotFoundError:
        return "zxing-cpp (version unknown)" if available() else "unavailable"


def available() -> bool:
    try:
        import zxingcpp  # noqa: F401
        return True
    except ImportError:
        return False


def _points(result) -> list[tuple[float, float]]:
    p = result.position
    corners = [p.top_left, p.top_right, p.bottom_right, p.bottom_left]
    return [(float(c.x), float(c.y)) for c in corners]


def _key(result) -> tuple[str, str]:
    return str(result.format), result.text


def read_image(image) -> list[Read]:
    """Decode all barcodes in a PIL image, including damaged ones the decoder could locate."""
    import zxingcpp

    rgb = image.convert("RGB")
    results = zxingcpp.read_barcodes(rgb, return_errors=True)
    reads: list[Read] = []
    for r in results:
        name = str(r.format)
        error = str(r.error) if r.error else ""
        read = Read(
            format_name=name, format_key=SUPPORTED.get(name), text=r.text if r.valid else (r.text or ""),
            raw_bytes=bytes(r.bytes or b""), valid=bool(r.valid), error=error,
            points=_points(r), orientation=float(r.orientation),
            inverted=bool(getattr(r, "is_inverted", False)), mirrored=bool(getattr(r, "is_mirrored", False)),
            ec_level=str(r.ec_level or ""), symbology_identifier=str(r.symbology_identifier or ""),
            content_type=str(r.content_type).split(".")[-1],
        )
        reads.append(read)

    # A "Code 39 Extended" read may really be standard Code 39 containing + or %; record both readings.
    for read in reads:
        if read.format_name == "Code 39 Extended" and read.valid:
            std = zxingcpp.read_barcodes(rgb, formats=zxingcpp.BarcodeFormat.Code39Std)
            if std:
                read.alternatives["code39_standard"] = std[0].text

    _measure_consistency(rgb, reads)
    return reads


def _measure_consistency(rgb, reads: list[Read]) -> None:
    """Re-read at other scales and count how many attempts reproduce each valid read exactly."""
    import zxingcpp
    from PIL import Image

    valid = [r for r in reads if r.valid]
    if not valid:
        return
    for scale in CONSISTENCY_SCALES:
        size = (max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale)))
        if size[0] * size[1] > 60_000_000:
            continue
        resized = rgb.resize(size, Image.Resampling.LANCZOS)
        found = {_key(r) for r in zxingcpp.read_barcodes(resized) if r.valid}
        for read in valid:
            read.attempts += 1
            if (read.format_name, read.text) in found:
                read.consistent_reads += 1

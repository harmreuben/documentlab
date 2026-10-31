"""Draws barcodes as PNG and SVG.

Each format uses a library dedicated to drawing it (python-barcode, segno, pdf417gen).
Verification later uses a separate decoder (zxing-cpp), so a passing round trip means two
independent implementations agree on the result.
"""
from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from .issues import Issues
from .symbologies import Symbology


@dataclass
class Rendered:
    png: bytes
    svg: str
    width: int
    height: int
    details: dict = field(default_factory=dict)  # e.g. QR version, PDF417 columns actually used


def render(symbology: Symbology, data: str, options: dict, issues: Issues) -> Rendered | None:
    try:
        if symbology.family == "linear":
            return _linear(symbology, data, options)
        if symbology.family == "matrix":
            return _qr(data, options, issues)
        return _pdf417(data, options, issues)
    except Exception as exc:  # a library refusing the data is reported, never hidden
        issues.error("payload", f"{symbology.name} could not be drawn: {exc}")
        return None


def _png_size(png: bytes) -> tuple[int, int]:
    from PIL import Image
    with Image.open(io.BytesIO(png)) as image:
        return image.size


# --- Linear codes -------------------------------------------------------------------------

def _linear(symbology: Symbology, data: str, o: dict) -> Rendered:
    import barcode
    from barcode.writer import ImageWriter, SVGWriter

    cls = barcode.get_barcode_class(symbology.key)
    extra = {"add_checksum": False} if symbology.key == "code39" else {}
    writer_options = {
        "module_width": o["module_width"],
        "module_height": o["bar_height"],
        "quiet_zone": o["quiet_zone"],
        "foreground": o["foreground"],
        "background": o["background"],
        "write_text": o["show_text"],
        "font_size": 10,
        "text_distance": 4.5,
    }
    png = io.BytesIO()
    cls(data, writer=ImageWriter(format="PNG"), **extra).write(png, options={**writer_options, "dpi": o["dpi"]})
    svg = io.BytesIO()
    cls(data, writer=SVGWriter(), **extra).write(svg, options=writer_options)
    png_bytes = png.getvalue()
    width, height = _png_size(png_bytes)
    return Rendered(png_bytes, _add_viewbox(svg.getvalue().decode("utf-8")), width, height)


_MM_SIZE = re.compile(r'<svg([^>]*?)width="([\d.]+)mm" height="([\d.]+)mm"')


def _add_viewbox(svg: str) -> str:
    """python-barcode sizes its SVG in millimetres with no viewBox, so it can't be scaled on screen.

    Adding a viewBox (1 mm = 96/25.4 px) keeps the printed size in millimetres while letting
    browsers and design tools scale the image cleanly.
    """
    def replace(match: re.Match) -> str:
        w, h = float(match.group(2)), float(match.group(3))
        px = 96 / 25.4
        return (f'<svg{match.group(1)}width="{match.group(2)}mm" height="{match.group(3)}mm" '
                f'viewBox="0 0 {w * px:.3f} {h * px:.3f}"')
    return _MM_SIZE.sub(replace, svg, count=1)


# --- QR -----------------------------------------------------------------------------------

def _qr(data: str, o: dict, issues: Issues) -> Rendered | None:
    import segno
    from segno import DataOverflowError

    try:
        code = segno.make(data, error=o["error_correction"].lower(), micro=False, boost_error=False)
    except DataOverflowError:
        issues.error("payload", "The data is too long for a QR code at this error correction level. "
                                "Shorten it or choose a lower level.")
        return None
    style = {"scale": o["module_size"], "border": o["border"], "dark": o["foreground"], "light": o["background"]}
    png, svg = io.BytesIO(), io.BytesIO()
    code.save(png, kind="png", **style)
    code.save(svg, kind="svg", xmldecl=False, svgns=True, **style)
    png_bytes = png.getvalue()
    width, height = _png_size(png_bytes)
    return Rendered(png_bytes, svg.getvalue().decode("utf-8"), width, height,
                    {"qr_version": code.designator})


# --- PDF417 -------------------------------------------------------------------------------

def _pdf417_encode(data: str, columns: int, level: int, issues: Issues):
    import pdf417gen

    try:
        return pdf417gen.encode(data, columns=columns, security_level=level), columns
    except ValueError as first:
        # Too few rows -> fewer columns; too many rows -> more columns.
        candidates = range(columns - 1, 0, -1) if "Minimum" in str(first) else range(columns + 1, 31)
        for cols in candidates:
            try:
                codes = pdf417gen.encode(data, columns=cols, security_level=level)
            except ValueError:
                continue
            issues.warning("columns", f"Columns changed from {columns} to {cols} so the data fits.")
            return codes, cols
    issues.error("payload", "The data is too long for PDF417 at this error correction level. "
                            "Shorten it or lower the level.")
    return None, columns


def _pdf417(data: str, o: dict, issues: Issues) -> Rendered | None:
    import pdf417gen

    codes, columns = _pdf417_encode(data, o["columns"], o["security_level"], issues)
    if codes is None:
        return None
    image = pdf417gen.render_image(codes, scale=o["module_size"], ratio=o["row_ratio"], padding=o["padding"],
                                   fg_color=o["foreground"], bg_color=o["background"])
    png = io.BytesIO()
    image.save(png, format="PNG")

    # pdf417gen's SVG has no background or margin, so wrap it in one with both.
    inner = pdf417gen.render_svg(codes, scale=o["module_size"], ratio=o["row_ratio"], color=o["foreground"]).getroot()
    pad = o["padding"]
    w, h = int(float(inner.get("width"))), int(float(inner.get("height")))
    svg = ET.Element("svg", {"xmlns": "http://www.w3.org/2000/svg", "version": "1.1",
                             "width": str(w + 2 * pad), "height": str(h + 2 * pad),
                             "viewBox": f"0 0 {w + 2 * pad} {h + 2 * pad}"})
    ET.SubElement(svg, "rect", {"width": "100%", "height": "100%", "fill": o["background"]})
    group = ET.SubElement(svg, "g", {"transform": f"translate({pad},{pad})"})
    for child in list(inner):
        group.append(child)
    return Rendered(png.getvalue(), ET.tostring(svg, encoding="unicode"), image.width, image.height,
                    {"pdf417_columns": columns, "pdf417_rows": len(codes)})

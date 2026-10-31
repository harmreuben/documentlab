"""Rendering options per barcode family, with their allowed ranges and defaults.

The frontend builds its controls from `option_specs()`, so the limits live in one place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .issues import Issues


@dataclass(frozen=True)
class OptionSpec:
    name: str
    label: str
    kind: str  # number | integer | choice | colour | boolean
    default: object
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None
    unit: str = ""
    choices: tuple[tuple[str, str], ...] = ()
    help: str = ""

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if v not in (None, "", ())}
        if self.choices:
            d["choices"] = [{"value": v, "label": label} for v, label in self.choices]
        return d


COLOURS = (
    OptionSpec("foreground", "Bar colour", "colour", "#000000"),
    OptionSpec("background", "Background", "colour", "#FFFFFF"),
)

LINEAR = (
    OptionSpec("module_width", "Narrow bar width", "number", 0.33, 0.19, 1.0, 0.01, "mm",
               help="0.33 mm is the standard size for retail codes."),
    OptionSpec("bar_height", "Bar height", "number", 15.0, 5.0, 50.0, 0.5, "mm"),
    OptionSpec("quiet_zone", "Quiet zone", "number", 6.5, 2.0, 20.0, 0.5, "mm",
               help="Blank margin either side. Scanners need it to find the code."),
    OptionSpec("dpi", "PNG resolution", "integer", 300, 72, 600, 1, "dpi"),
    OptionSpec("show_text", "Print the text under the bars", "boolean", True),
) + COLOURS

QR = (
    OptionSpec("error_correction", "Error correction", "choice", "M",
               choices=(("L", "Low (7%)"), ("M", "Medium (15%)"), ("Q", "Quartile (25%)"), ("H", "High (30%)")),
               help="Higher levels survive more damage but make a denser code."),
    OptionSpec("module_size", "Module size", "integer", 8, 1, 40, 1, "px"),
    OptionSpec("border", "Quiet zone", "integer", 4, 0, 10, 1, "modules",
               help="The QR standard asks for at least 4."),
) + COLOURS

PDF417 = (
    OptionSpec("security_level", "Error correction level", "integer", 2, 0, 8, 1,
               help="0 to 8. Each level roughly doubles the recovery data."),
    OptionSpec("columns", "Data columns", "integer", 6, 1, 30, 1,
               help="Adjusted automatically if the data needs a different shape."),
    OptionSpec("module_size", "Module width", "integer", 3, 1, 10, 1, "px"),
    OptionSpec("row_ratio", "Row height", "integer", 3, 2, 5, 1, "× module width"),
    OptionSpec("padding", "Quiet zone", "integer", 20, 0, 60, 1, "px"),
) + COLOURS

BY_FAMILY = {"linear": LINEAR, "matrix": QR, "stacked": PDF417}

_HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")


def option_specs(family: str) -> tuple[OptionSpec, ...]:
    return BY_FAMILY[family]


def _luminance(hex_colour: str) -> float:
    def channel(value: int) -> float:
        c = value / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def resolve_options(family: str, given: dict | None, issues: Issues) -> dict:
    """Apply defaults, check every value against its range, and check colour contrast."""
    given = dict(given or {})
    resolved: dict[str, object] = {}
    specs = option_specs(family)
    names = {s.name for s in specs}
    for unknown in sorted(set(given) - names):
        issues.warning(unknown, f"The option '{unknown}' doesn't apply to this format and was ignored.")

    for spec in specs:
        value = given.get(spec.name, spec.default)
        if value is None or value == "":
            value = spec.default
        if spec.kind in ("number", "integer"):
            try:
                number = float(value)
            except (TypeError, ValueError):
                issues.error(spec.name, f"{spec.label} must be a number.")
                continue
            if spec.kind == "integer" and not number.is_integer():
                issues.error(spec.name, f"{spec.label} must be a whole number.")
                continue
            if not (spec.minimum <= number <= spec.maximum):
                unit = f" {spec.unit}" if spec.unit else ""
                issues.error(spec.name, f"{spec.label} must be between {spec.minimum:g} and {spec.maximum:g}{unit}.")
                continue
            value = int(number) if spec.kind == "integer" else number
        elif spec.kind == "choice":
            if value not in {v for v, _ in spec.choices}:
                issues.error(spec.name, f"Choose a valid {spec.label.lower()}.")
                continue
        elif spec.kind == "colour":
            if not isinstance(value, str) or not _HEX.match(value):
                issues.error(spec.name, f"{spec.label} must be a colour like #1A2B3C.")
                continue
            value = value.upper()
        elif spec.kind == "boolean":
            if isinstance(value, str):
                value = value.strip().lower() in ("1", "true", "yes", "on")
            value = bool(value)
        resolved[spec.name] = value

    fg, bg = resolved.get("foreground"), resolved.get("background")
    if isinstance(fg, str) and isinstance(bg, str):
        if _luminance(fg) > _luminance(bg):
            issues.error("foreground", "Use dark bars on a light background. Most scanners can't read reversed codes.")
        else:
            ratio = contrast_ratio(fg, bg)
            if ratio < 3:
                issues.error("foreground", f"The colours are too close (contrast {ratio:.1f}:1). Most scanners need at least 3:1.")
            elif ratio < 7:
                issues.warning("foreground", f"Contrast is {ratio:.1f}:1. Some scanners struggle below 7:1.")

    if family == "matrix" and resolved.get("border", 4) < 4:
        issues.warning("border", "A quiet zone under 4 modules may stop some phones reading the code.")
    if family == "linear" and resolved.get("quiet_zone", 6.5) < 2.5:
        issues.warning("quiet_zone", "A very narrow quiet zone may stop handheld scanners finding the code.")
    return resolved

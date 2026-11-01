"""Image-quality indicators for barcode images.

Each indicator is a measurement plus a plain-language finding. Glare is not detected:
a simple brightness rule mistook white label backgrounds for glare, so it was removed
rather than left to raise false alarms (see the Phase 10 limitations list). The thresholds are
practical rules of thumb for scanning, not standards; they are written out here so
they can be reviewed and tuned, and each finding states the value it was based on.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

# Thresholds (reviewed in Phase 10 against the Testing Laboratory's fixture set).
MIN_LONG_SIDE_PX = 300       # images smaller than this rarely hold enough detail
MIN_SHORT_SIDE_PX = 60       # stacked codes are long and thin, so the short side is allowed to be small
BLUR_SHARPNESS_MIN = 100.0   # variance of the Laplacian at a 1000 px working size
CONTRAST_RANGE_MIN = 0.35    # spread between the 1st and 99th brightness percentiles (0-1)
DARK_MEAN_MAX = 0.25         # mean brightness below this = underexposed
EDGE_MARGIN_MIN_PX = 8       # a barcode closer than this to the edge may have lost its quiet zone
SKEW_TOLERANCE_DEG = 5       # angles further than this from 0/90/180/270 are reported


@dataclass
class Finding:
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


@dataclass
class QualityReport:
    width: int
    height: int
    sharpness: float
    contrast_range: float
    mean_brightness: float
    clipped_fraction: float
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def as_dict(self) -> dict:
        return {
            "width": self.width, "height": self.height,
            "sharpness": round(self.sharpness, 1),
            "contrast_range": round(self.contrast_range, 3),
            "mean_brightness": round(self.mean_brightness, 3),
            "clipped_fraction": round(self.clipped_fraction, 3),
            "findings": [f.as_dict() for f in self.findings],
        }


def _grey(image) -> np.ndarray:
    return np.asarray(image.convert("L"), dtype=np.float32) / 255.0


def assess_image(image) -> QualityReport:
    """Whole-image indicators: size, sharpness, contrast and exposure."""
    import cv2

    width, height = image.size
    grey = _grey(image)

    # Sharpness is measured at a fixed working size so that big photos aren't scored differently.
    scale = 1000 / max(width, height)
    working = cv2.resize(grey, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else grey
    sharpness = float(cv2.Laplacian((working * 255).astype(np.uint8), cv2.CV_64F).var())

    # 1st/99th percentiles: documents are mostly blank background, so narrower percentiles miss the text.
    p1, p99 = np.percentile(grey, [1, 99])
    contrast_range = float(p99 - p1)
    mean = float(grey.mean())
    clipped = float((grey >= 0.995).mean())

    report = QualityReport(width, height, sharpness, contrast_range, mean, clipped)
    f = report.findings
    if max(width, height) < MIN_LONG_SIDE_PX or min(width, height) < MIN_SHORT_SIDE_PX:
        f.append(Finding("low_resolution", f"The image is only {width} × {height} px. Scan at a higher resolution "
                                           f"(at least {MIN_LONG_SIDE_PX} px on the long side)."))
    if sharpness < BLUR_SHARPNESS_MIN:
        f.append(Finding("blurred", f"The image looks blurred (sharpness {sharpness:.0f}; "
                                    f"below {BLUR_SHARPNESS_MIN:.0f} is usually too soft). Hold the camera steady or refocus."))
    if contrast_range < CONTRAST_RANGE_MIN:
        f.append(Finding("low_contrast", f"Light and dark areas are too similar (range {contrast_range:.2f}). "
                                         "Improve lighting or print darker bars."))
    if mean < DARK_MEAN_MAX:
        f.append(Finding("underexposed", f"The image is very dark (average brightness {mean:.2f})."))
    return report


def tilt_degrees(points: list[tuple[float, float]]) -> float:
    """Angle of the barcode's top edge (top-left to top-right corner), in degrees."""
    (x1, y1), (x2, y2) = points[0], points[1]
    return math.degrees(math.atan2(y2 - y1, x2 - x1))


def assess_barcode(points: list[tuple[float, float]], image_size: tuple[int, int]) -> list[Finding]:
    """Indicators for one detected barcode: placement, size and angle."""
    width, height = image_size
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    findings = []
    margin = min(min(xs), min(ys), width - max(xs), height - max(ys))
    if margin < EDGE_MARGIN_MIN_PX:
        findings.append(Finding("near_edge", "The barcode touches the edge of the image, so its quiet zone may be cut off."))
    box_w, box_h = max(xs) - min(xs), max(ys) - min(ys)
    if max(box_w, box_h) < 60:
        findings.append(Finding("small_code", f"The barcode is only about {box_w:.0f} × {box_h:.0f} px in the image. "
                                              "Move closer or scan at a higher resolution."))
    off = abs(((tilt_degrees(points) + 45) % 90) - 45)
    if off > SKEW_TOLERANCE_DEG:
        findings.append(Finding("skewed", f"The barcode is tilted by about {off:.0f}°. It was read, but straight scans are more reliable."))
    return findings

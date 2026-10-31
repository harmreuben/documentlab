"""Barcode generation, validation and verification.

Pure Python: nothing here imports Django, so the same code runs in the web app,
the test suite and the Phase 11 desktop app.

    from core.barcodes import check, generate
    result = check("ean13", "590123412345", {})       # validate only
    output = generate("ean13", "590123412345", {})    # render PNG + SVG, then decode to verify
"""
from .engine import CheckResult, GenerateResult, check, generate
from .symbologies import SYMBOLOGIES, get_symbology

__all__ = ["CheckResult", "GenerateResult", "check", "generate", "SYMBOLOGIES", "get_symbology"]

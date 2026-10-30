"""DocumentLab - check that every Phase 2 Python library imports."""
import importlib

MODULES = [
    ("django", "Django"), ("rest_framework", "DRF"), ("drf_spectacular", "drf-spectacular"),
    ("environ", "django-environ"), ("PIL", "Pillow"), ("cv2", "OpenCV"), ("numpy", "NumPy"),
    ("pymupdf", "PyMuPDF"), ("barcode", "python-barcode"), ("segno", "segno"),
    ("pdf417gen", "pdf417gen"), ("zxingcpp", "zxing-cpp"), ("pytesseract", "pytesseract"),
    ("reportlab", "ReportLab"), ("pytest", "pytest"), ("pytest_django", "pytest-django"),
    ("factory", "factory-boy"),
]

bad = 0
for mod, name in MODULES:
    try:
        m = importlib.import_module(mod)
        version = getattr(m, "__version__", getattr(m, "VERSION", "installed"))
        print(f"[OK]      {name:<16} {version}")
    except Exception as exc:
        bad += 1
        print(f"[MISSING] {name:<16} {type(exc).__name__}: {exc}")

print(f"\n{len(MODULES) - bad}/{len(MODULES)} libraries import correctly")

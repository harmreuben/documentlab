"""Identifies uploaded files by their content, not by their name, and turns them into page images.

A file called "photo.png" that is really a PDF is treated as a PDF; a file that is
neither PNG, JPEG nor PDF is refused, whatever it is called.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

MAX_UPLOAD_BYTES = 10 * 1024 * 1024        # 10 MB
MAX_IMAGE_PIXELS = 40_000_000              # 40 megapixels; guards against "decompression bomb" images
MAX_PDF_PAGES = 10                         # pages analysed per PDF
PDF_RENDER_DPI = 200

KINDS = {"png": "image/png", "jpeg": "image/jpeg", "pdf": "application/pdf"}
EXTENSIONS = {"png": (".png",), "jpeg": (".jpg", ".jpeg"), "pdf": (".pdf",)}


class FileRejected(Exception):
    """The upload can't be analysed. The message is safe to show to the user."""


def sniff(head: bytes) -> str | None:
    """Return 'png', 'jpeg' or 'pdf' from the first bytes of a file, or None."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.lstrip()[:5] == b"%PDF-":
        return "pdf"
    return None


@dataclass
class Page:
    number: int          # 1-based
    image: object        # PIL.Image in RGB
    source: str          # "image" or "pdf"


@dataclass
class LoadedFile:
    kind: str
    pages: list[Page]
    page_count: int                       # pages in the file (may exceed those analysed)
    notes: list[str] = field(default_factory=list)


def check_upload(name: str, data: bytes) -> tuple[str, list[str]]:
    """Validate size and type. Returns (kind, warnings). Raises FileRejected."""
    if not data:
        raise FileRejected("The file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileRejected(f"The file is {len(data) / 1_048_576:.1f} MB. The limit is 10 MB.")
    kind = sniff(data[:16])
    if kind is None:
        raise FileRejected("Only PNG, JPEG and PDF files can be analysed. This file is none of those.")
    warnings = []
    if not name.lower().endswith(EXTENSIONS[kind]):
        warnings.append(f"The file name doesn't match its contents: it is really a {kind.upper()} file.")
    return kind, warnings


def load_pages(kind: str, data: bytes) -> LoadedFile:
    """Open the file and return the pages to analyse, as RGB images."""
    if kind == "pdf":
        return _pdf_pages(data)
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width * height > MAX_IMAGE_PIXELS:
                raise FileRejected(f"The image is {width} × {height} pixels. The limit is 40 megapixels.")
            image = ImageOps.exif_transpose(probe)  # phone photos store rotation in EXIF
            image = image.convert("RGB")
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise FileRejected("The image is damaged or incomplete and can't be opened.") from exc
    return LoadedFile(kind, [Page(1, image, "image")], 1)


def _pdf_pages(data: bytes) -> LoadedFile:
    import pymupdf
    from PIL import Image

    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise FileRejected("The PDF is damaged and can't be opened.") from exc
    with doc:
        if doc.needs_pass:
            raise FileRejected("The PDF is password-protected. Remove the password and upload it again.")
        if doc.page_count == 0:
            raise FileRejected("The PDF has no pages.")
        pages, notes = [], []
        for index in range(min(doc.page_count, MAX_PDF_PAGES)):
            pix = doc[index].get_pixmap(dpi=PDF_RENDER_DPI, alpha=False)
            if pix.width * pix.height > MAX_IMAGE_PIXELS:
                notes.append(f"Page {index + 1} is too large to render and was skipped.")
                continue
            pages.append(Page(index + 1, Image.frombytes("RGB", (pix.width, pix.height), pix.samples), "pdf"))
        if doc.page_count > MAX_PDF_PAGES:
            notes.append(f"Only the first {MAX_PDF_PAGES} of {doc.page_count} pages were analysed.")
        return LoadedFile("pdf", pages, doc.page_count, notes)

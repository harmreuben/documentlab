"""Builds synthetic test images on the fly (no real documents are ever used in tests)."""
import io

from PIL import Image, ImageEnhance, ImageFilter

from core.barcodes import generate

AAMVA_LIKE = "@\n\x1e\rANSI 636000080002DL00410278DLDAQT64235789\nDCSSAMPLE\nDBB01011990"


def barcode(fmt="ean13", data="590123412345", schema="documentlab.text.v1", fields=None, **options):
    return Image.open(io.BytesIO(generate(fmt, data, options, schema, fields).output.png)).convert("RGB")


def pdf417_raw(text: str):
    """PDF417 drawn directly, bypassing the generator's guard, to test the analyzer's handling."""
    import pdf417gen
    return pdf417gen.render_image(pdf417gen.encode(text, columns=8), scale=3).convert("RGB")


def as_png(image) -> bytes:
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def as_jpeg(image) -> bytes:
    out = io.BytesIO()
    image.save(out, "JPEG", quality=92)
    return out.getvalue()


def blurred(image):
    return image.filter(ImageFilter.GaussianBlur(3))


def low_contrast(image):
    return ImageEnhance.Contrast(image).enhance(0.15)


def on_canvas(*images, size=(1200, 900)):
    canvas = Image.new("RGB", size, "white")
    x = 60
    for im in images:
        canvas.paste(im, (x, 120))
        x += im.width + 80
    return canvas


def pdf_with(images, blank_first=False) -> bytes:
    import pymupdf
    doc = pymupdf.open()
    if blank_first:
        doc.new_page()
    for im in images:
        page = doc.new_page()
        page.insert_image(pymupdf.Rect(72, 72, 72 + im.width * 0.6, 72 + im.height * 0.6), stream=as_png(im))
    return doc.tobytes()

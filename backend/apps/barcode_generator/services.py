"""Generation workflows: one barcode, a CSV batch, and the printable PDF sheet."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.db import transaction

from core.barcodes import generate
from core.barcodes.schemas import TEXT_SCHEMA, get_schema

from .models import GeneratedBarcode, GenerationBatch, new_test_reference

MAX_BATCH_ROWS = 500
MAX_BATCH_BYTES = 1024 * 1024  # 1 MB


class GenerationRefused(Exception):
    """The input failed validation. `result` holds the field errors to show."""

    def __init__(self, result):
        super().__init__("Generation refused")
        self.result = result


def create_barcode(*, user, format_key: str, payload: str | None, options: dict | None,
                   schema_id: str = TEXT_SCHEMA, fields: dict | None = None, label: str = "",
                   batch: GenerationBatch | None = None, batch_row: int | None = None) -> GeneratedBarcode:
    result = generate(format_key, payload, options, schema_id, fields)
    if not result.ok:
        raise GenerationRefused(result.check)

    out, checked, verified = result.output, result.check, result.verification
    structured = get_schema(checked.schema).structured
    reference = new_test_reference()
    while GeneratedBarcode.objects.filter(test_reference=reference).exists():
        reference = new_test_reference()

    record = GeneratedBarcode(
        test_reference=reference, created_by=user, batch=batch, batch_row=batch_row,
        format=checked.format, schema_id=checked.schema, label=(label or "")[:80],
        input_payload="" if structured else (payload or ""),
        input_fields=(fields or {}) if structured else {},
        expected_decode=checked.expected_decode, check_digit=checked.check_digit or "",
        options=checked.options, render_details=out.details, warnings=checked.warnings,
        png_sha256=hashlib.sha256(out.png).hexdigest(), width_px=out.width, height_px=out.height,
        verification_status=verified.status, decoded_text=verified.decoded_text,
        decoded_format=verified.decoded_format or "", verification_detail=verified.detail[:255],
    )
    record.png.save(f"{reference}.png", ContentFile(out.png), save=False)
    record.svg.save(f"{reference}.svg", ContentFile(out.svg.encode("utf-8")), save=False)
    record.save()
    return record


# --- Batches ------------------------------------------------------------------------------

@dataclass
class BatchProblem(Exception):
    message: str


def _read_csv(raw: bytes) -> list[dict]:
    if len(raw) > MAX_BATCH_BYTES:
        raise BatchProblem("The file is larger than 1 MB. Split it into smaller files.")
    if b"\x00" in raw:
        raise BatchProblem("This doesn't look like a CSV text file.")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise BatchProblem("Save the CSV as UTF-8 and upload it again.") from None
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    if "format" not in headers:
        raise BatchProblem("The CSV needs a 'format' column. Download the template to see the layout.")
    reader.fieldnames = headers
    rows = []
    for row in reader:
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue  # skip blank lines
        rows.append({k: (v if isinstance(v, str) else "") for k, v in row.items() if k})
        if len(rows) > MAX_BATCH_ROWS:
            raise BatchProblem(f"The file has more than {MAX_BATCH_ROWS} rows. Split it into smaller files.")
    if not rows:
        raise BatchProblem("The CSV has no data rows.")
    return rows


def run_batch(*, user, filename: str, raw: bytes, options: dict | None) -> GenerationBatch:
    rows = _read_csv(raw)
    batch = GenerationBatch.objects.create(created_by=user, source_name=filename[:200], options=options or {},
                                           total_rows=len(rows))
    report = []
    for number, row in enumerate(rows, start=2):  # row 1 is the header
        format_key = row.get("format", "").strip().lower()
        schema_id = row.get("schema", "").strip() or TEXT_SCHEMA
        schema = get_schema(schema_id)
        fields = None
        if schema is not None and schema.structured:
            fields = {f.name: row.get(f.name, "") for f in schema.fields}
        entry = {"row": number, "format": format_key, "schema": schema_id, "label": row.get("label", "").strip()}
        try:
            with transaction.atomic():
                record = create_barcode(user=user, format_key=format_key, payload=row.get("payload", ""),
                                        options=options, schema_id=schema_id, fields=fields,
                                        label=entry["label"], batch=batch, batch_row=number)
            entry.update(status="GENERATED", test_reference=record.test_reference,
                         verification=record.verification_status, expected_decode=record.expected_decode, message="")
        except GenerationRefused as refused:
            entry.update(status="REJECTED", test_reference="", verification="",
                         expected_decode="", message="; ".join(e["message"] for e in refused.result.errors))
        report.append(entry)

    batch.report = report
    batch.succeeded = sum(1 for e in report if e["status"] == "GENERATED")
    batch.failed = len(report) - batch.succeeded
    batch.save(update_fields=["report", "succeeded", "failed"])
    return batch


def _safe_cell(value) -> str:
    """Stop spreadsheet programs treating a cell as a formula (CSV injection)."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def batch_report_csv(batch: GenerationBatch) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["row", "format", "schema", "label", "status", "test_reference", "verification",
                     "expected_decode", "message"])
    for e in batch.report:
        writer.writerow([_safe_cell(e.get(k)) for k in ("row", "format", "schema", "label", "status",
                                                         "test_reference", "verification", "expected_decode", "message")])
    return out.getvalue()


def batch_zip(batch: GenerationBatch) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.csv", batch_report_csv(batch))
        for record in batch.barcodes.order_by("batch_row"):
            with record.png.open("rb") as f:
                archive.writestr(f"png/{record.test_reference}.png", f.read())
            with record.svg.open("rb") as f:
                archive.writestr(f"svg/{record.test_reference}.svg", f.read())
        archive.writestr("labels.pdf", labels_pdf(list(batch.barcodes.order_by("batch_row"))))
    return buffer.getvalue()


# --- Printable labels ---------------------------------------------------------------------

def labels_pdf(records: list[GeneratedBarcode]) -> bytes:
    """A4 sheet, one label per barcode, two columns. Each label states it is synthetic test output."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.setTitle("DocumentLab barcode labels")
    pdf.setAuthor("DocumentLab")
    page_w, page_h = A4
    margin, gap = 14 * mm, 8 * mm
    cell_w = (page_w - 2 * margin - gap) / 2
    cell_h = 62 * mm
    per_page = 2 * int((page_h - 2 * margin + gap) // (cell_h + gap))

    for index, record in enumerate(records):
        if index and index % per_page == 0:
            pdf.showPage()
        slot = index % per_page
        col, row = slot % 2, slot // 2
        x = margin + col * (cell_w + gap)
        y_top = page_h - margin - row * (cell_h + gap)

        pdf.setStrokeColorRGB(0.86, 0.88, 0.91)
        pdf.roundRect(x, y_top - cell_h, cell_w, cell_h, 3 * mm)

        with record.png.open("rb") as f:
            image = ImageReader(io.BytesIO(f.read()))
        iw, ih = image.getSize()
        box_w, box_h = cell_w - 10 * mm, cell_h - 26 * mm
        scale = min(box_w / iw, box_h / ih)
        dw, dh = iw * scale, ih * scale
        pdf.drawImage(image, x + (cell_w - dw) / 2, y_top - 6 * mm - dh, dw, dh)

        pdf.setFillColorRGB(0.06, 0.09, 0.15)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(x + 5 * mm, y_top - cell_h + 13 * mm, record.test_reference)
        pdf.setFont("Helvetica", 8)
        detail = f"{record.format.upper()}  ·  {record.label}" if record.label else record.format.upper()
        pdf.drawString(x + 5 * mm, y_top - cell_h + 9 * mm, detail[:70])
        pdf.setFillColorRGB(0.36, 0.4, 0.47)
        pdf.setFont("Helvetica", 6.5)
        pdf.drawString(x + 5 * mm, y_top - cell_h + 4.5 * mm,
                       f"Synthetic test barcode · verification {record.verification_status}")
    pdf.save()
    return buffer.getvalue()

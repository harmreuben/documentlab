"""Synthetic sample data for every format and schema.

All values are fictional and marked TEST. Retail numbers use the GS1 ranges reserved
for internal use (EAN prefix 2, UPC number system 4), so they can never clash with a
real product.
"""
from __future__ import annotations

import random
from datetime import date, timedelta

from .schemas import TEXT_SCHEMA

_ITEMS = ["Bench scanner", "Label printer", "Calibration card", "Test laptop", "Handheld reader"]
_PLACES = ["Lab bench 2", "Store room A", "QA shelf 4", "Dispatch desk"]
_DEPOTS = ["Depot North", "Depot East", "Depot South", "Depot West", "Central hub"]


def sample(format_key: str, schema_id: str = TEXT_SCHEMA, seed: int | None = None) -> dict:
    """Return {"payload": "..."} for plain text, or {"fields": {...}} for a structured schema."""
    rnd = random.Random(seed)
    n = rnd.randint(1, 9999)

    if schema_id == "documentlab.asset-tag.v1":
        acquired = date(2024, 1, 1) + timedelta(days=rnd.randint(0, 900))
        return {"fields": {"asset_id": f"TEST-AST-{n:04d}", "name": rnd.choice(_ITEMS),
                           "location": rnd.choice(_PLACES), "acquired": acquired.isoformat()}}
    if schema_id == "documentlab.shipment-label.v1":
        origin, destination = rnd.sample(_DEPOTS, 2)
        return {"fields": {"shipment_ref": f"TEST-SHP-{n:04d}", "origin": origin, "destination": destination,
                           "pieces": str(rnd.randint(1, 40)), "weight_kg": str(round(rnd.uniform(0.5, 900), 1))}}
    if schema_id == "documentlab.test-fixture.v1":
        return {"fields": {"test_id": f"TEST-FX-{n:04d}", "description": "Round-trip check of a synthetic label",
                           "expected_result": rnd.choice(["PASS", "FAIL"]), "notes": "Synthetic data. Not a real record."}}

    def digits(count: int) -> str:
        return "".join(str(rnd.randint(0, 9)) for _ in range(count))

    payload = {
        "qr": f"https://example.test/items/TEST-{n:04d}",
        "code128": f"DL-TEST-{n:06d}",
        "code39": f"TEST-{n:05d}",
        "ean13": "2" + digits(11),
        "ean8": "2" + digits(6),
        "upca": "4" + digits(10),
        "pdf417": f"DocumentLab synthetic test payload TEST-{n:04d}. Not real data.",
    }.get(format_key, f"TEST-{n:04d}")
    return {"payload": payload}

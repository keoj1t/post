import logging
from typing import Any

from fastapi import Body, FastAPI

from app.parser import parse_address
from app.auth import router as auth_router

from pathlib import Path
from fastapi.responses import FileResponse



log = logging.getLogger("jana")
app = FastAPI(title="Jana Address")
app.include_router(auth_router)
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")
FIELDS = [
    "province", "city", "district", "living_area", "street_type",
    "street_name", "house", "apartment", "entrance", "floor", "landmark",
]
LIST_KEYS = ("records", "data", "items", "addresses")


def as_record(item: Any) -> dict:
    """Любой элемент превращаем в запись: строка = raw_address, мусор = пустая запись."""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        return {"raw_address": item}
    return {}


def extract_records(payload: Any) -> list:
    """Принимает голый список, {"records": [...]} и одиночную запись."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in LIST_KEYS:
            if isinstance(payload.get(key), list):
                return payload[key]
        if "raw_address" in payload:
            return [payload]
    return []


def parse_one(item: Any) -> dict:
    rec = as_record(item)
    raw = rec.get("raw_address")
    if raw is not None and not isinstance(raw, str):
        raw = str(raw)
    out = {"id": rec.get("id"), "raw_address": raw}
    for f in FIELDS:
        out[f] = None
    out["confidence"] = 0.0
    try:
        parsed = parse_address(raw or "")
        for f in FIELDS:
            out[f] = parsed.get(f)
        out["confidence"] = parsed.get("confidence", 0.0)
    except Exception:
        log.exception("parse failed for id=%s", rec.get("id"))
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/parse")
def parse_single(payload: Any = Body(...)):
    records = extract_records(payload)
    return parse_one(records[0] if records else payload)


@app.post("/parse/batch")
def parse_batch(payload: Any = Body(...)):
    # ответ всегда содержит ровно столько записей, сколько пришло, в том же порядке
    return [parse_one(r) for r in extract_records(payload)]
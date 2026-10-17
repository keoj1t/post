import logging
import os
import json
import re
from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import urlopen
from typing import Any

from fastapi import Body, FastAPI, HTTPException

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
    "street_name", "house", "apartment", "entrance", "floor", "landmark", "postal_code", "building", "structure",
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
        out['review'] = parsed.get('review', {'needs_review': True, 'issues': []})
    except Exception:
        log.exception("parse failed for id=%s", rec.get("id"))
    return out


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/map/config")
def map_config():
    return {"enabled": bool(os.getenv("JANA_2GIS_API_KEY")), "key": os.getenv("JANA_2GIS_API_KEY")}


def _two_gis_request(params: dict, key: str) -> dict:
    query = {**params, "key": key, "locale": "ru_KZ"}
    url = "https://catalog.api.2gis.com/3.0/items/geocode?" + urlencode(query)
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read())


@lru_cache(maxsize=64)
def _two_gis_city_id(city: str, key: str) -> str | None:
    data = _two_gis_request({"q": city, "type": "adm_div.city", "fields": "items.id", "page_size": 1}, key)
    items = data.get("result", {}).get("items", [])
    return items[0].get("id") if items else None


def _map_street_key(value: str) -> str:
    value = value.lower().replace("ё", "е").translate(str.maketrans("әіңғүұқөһ", "аингуукох"))
    value = re.sub(r"\b(?:улица|ул|проспект|пр-т|просп|переулок|пер|бульвар|шоссе|көшесі|көше|даңғылы|street|avenue|road)\b", " ", value)
    return re.sub(r"[^\w]+", "", value)


def _address_parts(item: dict) -> tuple[str, str]:
    components = (item.get("address") or {}).get("components") or []
    streets = [str(c.get("street", "")) for c in components if c.get("street")]
    numbers = [str(c.get("number", "")) for c in components if c.get("type") == "street_number" and c.get("number")]
    return " ".join(streets), " ".join(numbers)


def _number_key(value: str) -> str:
    return re.sub(r"\s+", "", value.lower().replace("ё", "е")).strip(".,")


@app.get("/map/geocode")
def map_geocode(q: str):
    key = os.getenv("JANA_2GIS_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="2GIS map is not configured")
    if not q.strip() or len(q) > 500:
        raise HTTPException(status_code=400, detail="Address must contain 1 to 500 characters")
    try:
        from app.parser import parse_address
        parsed = parse_address(q)
        city, street, house = parsed.get("city"), parsed.get("street_name"), parsed.get("house")
        if not city or not street:
            return {"found": False, "reason": "city_or_street_missing"}
        city_id = _two_gis_city_id(city, key)
        if not city_id:
            return {"found": False, "reason": "city_not_found"}

        street_query = " ".join(filter(None, (parsed.get("street_type"), street)))
        query = f"{street_query}, {house}" if house else street_query
        fields = "items.point,items.full_name,items.address,items.type,items.subtype"
        wanted_street = _map_street_key(street)
        house_key = _number_key(str(house)) if house else None
        exact = []
        for page in range(1, 4):
            payload = _two_gis_request({"q": query, "city_id": city_id, "fields": fields, "page_size": 10, "page": page}, key)
            items = payload.get("result", {}).get("items", [])
            for item in items:
                point = item.get("point")
                if not point or not isinstance(point.get("lat"), (int, float)) or not isinstance(point.get("lon"), (int, float)):
                    continue
                result_street, result_house = _address_parts(item)
                if wanted_street and _map_street_key(result_street) == wanted_street:
                    result_numbers = {_number_key(number) for number in result_house.split()}
                    if house_key and house_key in result_numbers and item.get("type") == "building":
                        exact.append(item)
            if exact or len(items) < 10 or page * 10 >= payload.get("result", {}).get("total", 0):
                break
        if exact:
            item = exact[0]
            precision = "house"
        else:
            street_payload = _two_gis_request({"q": street_query, "city_id": city_id, "type": "street", "fields": fields, "page_size": 10}, key)
            street_items = street_payload.get("result", {}).get("items", [])
            item = next((x for x in street_items if x.get("type") == "street" and _map_street_key(x.get("name", "")) == wanted_street and x.get("point")), None)
            if not item:
                return {"found": False, "reason": "street_or_house_not_found"}
            precision = "street"
    except Exception as exc:
        log.warning("2GIS geocoding failed: %s", exc)
        raise HTTPException(status_code=502, detail="2GIS geocoding is unavailable") from exc
    point = item["point"]
    return {"found": True, "coordinates": [point["lon"], point["lat"]], "name": item.get("full_name") or item.get("name"), "precision": precision}


@app.post("/parse")
def parse_single(payload: Any = Body(...)):
    records = extract_records(payload)
    return parse_one(records[0] if records else payload)


@app.post("/parse/batch")
def parse_batch(payload: Any = Body(...)):
    return [parse_one(r) for r in extract_records(payload)]

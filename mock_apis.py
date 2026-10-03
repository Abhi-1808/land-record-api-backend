"""
Mock government API endpoints for local development.

Changes from original:
- All JSON files are loaded ONCE at module import time rather than on every
  request. This eliminates repeated disk I/O and makes endpoints constant-time.
- GIS parcel lookup is now a plain dict.get() against the pre-loaded dict.
"""

import json
import os
from functools import lru_cache

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["mock-government-apis"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# Load all datasets once at startup — no disk I/O per request.
try:
    _LRMS: list = _load("synthetic_lrms.json")
    _REGISTRATION: list = _load("synthetic_registration.json")
    _MUTATION: list = _load("synthetic_mutation.json")
    _GIS: dict = _load("synthetic_gis.json")
    _ENCUMBRANCE: list = _load("synthetic_encumbrance.json")
except FileNotFoundError as exc:
    raise RuntimeError(f"Mock data file missing: {exc}") from exc

# Build lookup indexes so route handlers are O(1).
_LRMS_IDX: dict = {r["property_id"]: r for r in _LRMS if "property_id" in r}
_REG_IDX: dict = {r["registration_no"]: r for r in _REGISTRATION if "registration_no" in r}
_MUT_IDX: dict = {r.get("mutation_no", r.get("id", "")): r for r in _MUTATION}


@router.get("/lrms/properties/{property_id}")
def get_lrms_property(property_id: str):
    record = _LRMS_IDX.get(property_id)
    if not record:
        raise HTTPException(status_code=404, detail="Property not found in LRMS")
    return record


@router.get("/registration/{registration_no}")
def get_registration(registration_no: str):
    record = _REG_IDX.get(registration_no)
    if not record:
        raise HTTPException(status_code=404, detail="Registration not found")
    return record


@router.get("/mutations/{mutation_no}")
def get_mutation(mutation_no: str):
    record = _MUT_IDX.get(mutation_no)
    if not record:
        raise HTTPException(status_code=404, detail="Mutation not found")
    return record


@router.get("/v1/gis/parcels/{parcel_id}")
def get_gis_parcel(parcel_id: str):
    record = _GIS.get(parcel_id)
    if record is None:
        raise HTTPException(status_code=404, detail="GIS parcel not found")
    from rules_engine import validate_gis_geometry
    validation = validate_gis_geometry(record)
    return {**record, "computed_area_acres": validation["area_acres"], "spatial_validation": validation}

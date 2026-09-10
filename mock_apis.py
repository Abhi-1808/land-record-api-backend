import json
import os
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api", tags=["mock-government-apis"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/lrms/properties/{property_id}")
def get_lrms_property(property_id: str):
    records = load_json("synthetic_lrms.json")
    for record in records:
        if record["property_id"] == property_id:
            return record
    raise HTTPException(status_code=404, detail="Property not found in LRMS")


@router.get("/registration/{registration_no}")
def get_registration(registration_no: str):
    records = load_json("synthetic_registration.json")
    for record in records:
        if record["registration_no"] == registration_no:
            return record
    raise HTTPException(status_code=404, detail="Registration not found")


@router.get("/mutations/{mutation_no}")
def get_mutation(mutation_no: str):
    records = load_json("synthetic_mutation.json")
    for record in records:
        if record["mutation_no"] == mutation_no:
            return record
    raise HTTPException(status_code=404, detail="Mutation not found")
import json
import os
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from rules_engine import compare_field, run_business_rules, run_cross_field_checks, run_additional_business_rules, decide_outcome
from database import verification_logs_collection

router = APIRouter(prefix="/api/verification", tags=["verification"])

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_json(filename: str):
    path = os.path.join(DATA_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_lrms_property(property_id: str):
    for record in load_json("synthetic_lrms.json"):
        if record["property_id"] == property_id:
            return record
    return None


def find_mutation(property_id: str):
    for record in load_json("synthetic_mutation.json"):
        if record["property_id"] == property_id:
            return record
    return None


def find_registration(registration_no: str):
    for record in load_json("synthetic_registration.json"):
        if record["registration_no"] == registration_no:
            return record
    return None


def find_encumbrance(property_id: str):
    for record in load_json("synthetic_encumbrance.json"):
        if record["property_id"] == property_id:
            active = any(e["status"] == "ACTIVE" for e in record.get("encumbrances", []))
            return active
    return False


class ExtractedFields(BaseModel):
    property_id: str
    owner_name: Optional[str] = None
    survey_no: Optional[str] = None
    area: Optional[float] = None
    area_unit: Optional[str] = None
    village: Optional[str] = None
    registration_no: Optional[str] = None
    sale_date: Optional[str] = None
    registration_date: Optional[str] = None
    mutation_date: Optional[str] = None
    owner_shares: Optional[List[float]] = None
    seller_name: Optional[str] = None
    consideration_amount: Optional[float] = None
    claimed_previous_owner: Optional[str] = None


@router.post("/document")
def verify_document(fields: ExtractedFields):
    lrms_record = find_lrms_property(fields.property_id)

    if lrms_record is None:
        verification_logs_collection.insert_one({
            "property_id": fields.property_id,
            "input_fields": fields.dict(),
            "result": "PROPERTY_NOT_FOUND",
            "timestamp": datetime.utcnow()
        })
        raise HTTPException(status_code=404, detail="Property not found in LRMS — cannot verify")

    lrms_owner_name = lrms_record["owners"][0]["name"] if lrms_record.get("owners") else None

    field_results = [
        compare_field("owner_name", fields.owner_name, lrms_owner_name),
        compare_field("survey_no", fields.survey_no, lrms_record.get("survey_no")),
        compare_field("area", fields.area, lrms_record.get("area"), tolerance=0.01),
        compare_field("village", fields.village, lrms_record.get("village")),
    ]

    if fields.registration_no:
        registration_record = find_registration(fields.registration_no)
        field_results.append(
            compare_field(
                "registration_no",
                fields.registration_no,
                registration_record["registration_no"] if registration_record else None
            )
        )

    mutation_record = find_mutation(fields.property_id)
    mutation_status = mutation_record["status"] if mutation_record else None

    encumbrance_active = find_encumbrance(fields.property_id)

    flags = run_business_rules(field_results, encumbrance_active=encumbrance_active, mutation_status=mutation_status)

    # Run cross-field checks and merge in any additional flags
    cross_field_flags = run_cross_field_checks(
        sale_date=fields.sale_date,
        registration_date=fields.registration_date,
        mutation_date=fields.mutation_date,
        owner_shares=fields.owner_shares
    )
    current_owner_names = [o["name"] for o in lrms_record.get("owners", [])]

    additional_flags = run_additional_business_rules(
        property_status=lrms_record.get("status"),
        seller_name=fields.seller_name,
        current_owner_names=current_owner_names,
        consideration_amount=fields.consideration_amount,
        sale_date=fields.sale_date,
        registration_date=fields.registration_date,
        extracted_area_unit=fields.area_unit,
        authoritative_area_unit=lrms_record.get("area_unit"),
        claimed_previous_owner=fields.claimed_previous_owner,
        last_mutation_new_owner=mutation_record.get("new_owner") if mutation_record else None
    )
    flags.extend(additional_flags)
    flags.extend(cross_field_flags)

    outcome = decide_outcome(flags, field_results)

    result = {
        "property_id": fields.property_id,
        "fields": field_results,
        "mutation_status": mutation_status,
        "encumbrance_active": encumbrance_active,
        "flags": flags,
        "decision": outcome["decision"],
        "review_reason": outcome["reason"]
    }

    log_entry = {
        **result,
        "input_fields": fields.dict(),
        "timestamp": datetime.utcnow()
    }
    log_result = verification_logs_collection.insert_one(log_entry)
    result["log_id"] = str(log_result.inserted_id)

    return result
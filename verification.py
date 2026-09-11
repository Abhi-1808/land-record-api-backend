import json
import os
from uuid import uuid4
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List

from rules_engine import calculate_overall_confidence, compare_field, run_business_rules, run_cross_field_checks, run_additional_business_rules, decide_outcome, validate_gis_geometry
from database import case_collection, verification_logs_collection
from duplicate_engine import find_duplicate_candidates
from blockchain import commit_review_decision

router = APIRouter(prefix="/api/verification", tags=["verification"])
case_router = APIRouter(prefix="/api/v1/verification", tags=["verification-cases"])

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


def find_gis_parcel(property_id: str):
    records = load_json("synthetic_gis.json")
    return records.get(property_id)


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


class ReviewAction(BaseModel):
    reviewer_id: str
    reason: str


def _as_dict(fields: ExtractedFields) -> dict:
    return fields.model_dump() if hasattr(fields, "model_dump") else fields.dict()


def _save_case(result: dict, fields: ExtractedFields) -> str:
    case_id = str(uuid4())
    if result["decision"] == "AUTO_APPROVE":
        status = "AUTO_APPROVED"
    elif result["decision"] == "REJECT":
        status = "REJECTED"
    else:
        status = "HUMAN_REVIEW_REQUIRED"
    case_collection.insert_one({
        "case_id": case_id,
        "status": status,
        "property_id": fields.property_id,
        "extracted_fields": _as_dict(fields),
        "audit_bundle": result,
        "created_at": datetime.utcnow(),
    })
    return case_id


@router.post("/document")
def verify_document(fields: ExtractedFields):
    lrms_record = find_lrms_property(fields.property_id)

    if lrms_record is None:
        verification_logs_collection.insert_one({
            "property_id": fields.property_id,
            "input_fields": _as_dict(fields),
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

    gis_record = find_gis_parcel(fields.property_id)
    gis_validation = validate_gis_geometry(gis_record, lrms_record.get("area"))
    if gis_validation["flag"]:
        flags.append(gis_validation["flag"])

    historical_records = (
        verification_logs_collection.all()
        if hasattr(verification_logs_collection, "all")
        else list(verification_logs_collection.find({}))
    )
    historical_records = [
        {**record.get("input_fields", {}), "property_id": record.get("property_id")}
        for record in historical_records
    ]
    duplicate_candidates = find_duplicate_candidates(_as_dict(fields), historical_records)
    flags.extend(candidate["flag"] for candidate in duplicate_candidates[:1])

    outcome = decide_outcome(flags, field_results)
    overall_confidence = calculate_overall_confidence(field_results)

    result = {
        "property_id": fields.property_id,
        "fields": field_results,
        "mutation_status": mutation_status,
        "encumbrance_active": encumbrance_active,
        "flags": flags,
        "decision": outcome["decision"],
        "review_reason": outcome["reason"]
        ,"overall_confidence": overall_confidence
        ,"gis_validation": gis_validation
        ,"duplicate_candidates": duplicate_candidates
    }

    log_entry = {
        **result,
        "input_fields": _as_dict(fields),
        "timestamp": datetime.utcnow()
    }
    log_result = verification_logs_collection.insert_one(log_entry)
    result["log_id"] = str(log_result.inserted_id)
    result["case_id"] = _save_case(result, fields)

    return result


@case_router.get("/cases")
def list_cases(status: Optional[str] = None):
    cases = case_collection.all() if hasattr(case_collection, "all") else list(case_collection.find({}))
    if status:
        cases = [case for case in cases if case.get("status") == status]
    return [{**case, "_id": str(case["_id"])} for case in cases]


@case_router.get("/cases/{case_id}")
def get_case(case_id: str):
    case = case_collection.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Verification case not found")
    return {**case, "_id": str(case["_id"])}


def _review_case(case_id: str, action: ReviewAction, status: str):
    case = case_collection.find_one({"case_id": case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Verification case not found")
    chain_result = commit_review_decision(case_id, status, action.reviewer_id, action.reason)
    review = {
        "reviewer_id": action.reviewer_id,
        "review_reason": action.reason,
        "reviewed_at": datetime.utcnow(),
        "blockchain": chain_result,
    }
    case_collection.update_one({"case_id": case_id}, {"$set": {"status": status, "review": review}})
    return {**case, "status": status, "review": review, "_id": str(case["_id"])}


@case_router.post("/cases/{case_id}/approve")
def approve_case(case_id: str, action: ReviewAction):
    return _review_case(case_id, action, "MANUALLY_APPROVED")


@case_router.post("/cases/{case_id}/reject")
def reject_case(case_id: str, action: ReviewAction):
    return _review_case(case_id, action, "REJECTED")
from datetime import datetime
from typing import Optional

from rapidfuzz import fuzz
from shapely.geometry import shape


FIELD_WEIGHTS = {
    "owner_name": 0.35,
    "survey_no": 0.35,
    "area": 0.15,
    "village": 0.15,
}


def _similarity(extracted_value, authoritative_value, tolerance: float) -> float:
    if extracted_value is None or authoritative_value is None:
        return 0.0
    if isinstance(extracted_value, (int, float)) and isinstance(authoritative_value, (int, float)):
        difference = abs(float(extracted_value) - float(authoritative_value))
        if difference <= tolerance:
            return 1.0
        return max(0.0, 1.0 - difference / max(abs(float(authoritative_value)), 1.0))
    return fuzz.token_sort_ratio(str(extracted_value), str(authoritative_value)) / 100


def _confidence_status(score: float) -> str:
    if score >= 0.90:
        return "MATCH"
    if score >= 0.70:
        return "LOW_CONFIDENCE"
    return "MISMATCH"


def validate_field_format(field_name: str, value) -> Optional[str]:
    """
    Checks a field's standalone validity — independent of any external match.
    Returns an error string if invalid, or None if the field looks fine
    (or doesn't have a specific format rule).
    """
    if value is None or value == "":
        return None  # missing-ness is handled separately, not a format issue

    if field_name == "area":
        if not isinstance(value, (int, float)):
            return "AREA_NOT_NUMERIC"
        if value <= 0:
            return "AREA_NOT_POSITIVE"
        if value > 1000:  # sanity ceiling — adjust based on realistic parcel sizes
            return "AREA_IMPLAUSIBLY_LARGE"

    if field_name in ("sale_date", "registration_date", "mutation_date"):
        if parse_date(value) is None:
            return "INVALID_DATE_FORMAT"

    if field_name == "survey_no":
        # Basic sanity check: should contain at least one digit
        if not any(char.isdigit() for char in str(value)):
            return "SURVEY_NO_FORMAT_INVALID"

    return None


def compare_field(field_name: str, extracted_value, authoritative_value, tolerance: float = 0.0) -> dict:
    """
    Compares a single extracted field against its authoritative counterpart,
    and separately checks the field's own standalone validity.

    Status values (matches the DILRMP-style 5-state vocabulary):
    - VERIFIED               → matches authoritative value, valid format
    - PARTIALLY_VERIFIED     → valid format, but authoritative source unavailable to fully confirm
    - MISMATCH               → doesn't match authoritative value
    - NOT_FOUND              → value provided but no authoritative record exists to compare against
    - VERIFICATION_UNAVAILABLE → value missing, or format itself is invalid, so verification can't proceed
    """
    format_error = validate_field_format(field_name, extracted_value)

    if extracted_value is None or extracted_value == "":
        return {
            "field": field_name,
            "extracted": extracted_value,
            "authoritative": authoritative_value,
            "extracted_value": extracted_value,
            "verified_value": authoritative_value,
            "confidence_score": 0.0,
            "field_status": "MISMATCH",
            "status": "VERIFICATION_UNAVAILABLE",
            "issue": "FIELD_MISSING"
        }

    if format_error:
        return {
            "field": field_name,
            "extracted": extracted_value,
            "authoritative": authoritative_value,
            "extracted_value": extracted_value,
            "verified_value": authoritative_value,
            "confidence_score": 0.0,
            "field_status": "MISMATCH",
            "status": "VERIFICATION_UNAVAILABLE",
            "issue": format_error
        }

    if authoritative_value is None:
        return {
            "field": field_name,
            "extracted": extracted_value,
            "authoritative": authoritative_value,
            "extracted_value": extracted_value,
            "verified_value": authoritative_value,
            "confidence_score": 0.0,
            "field_status": "MISMATCH",
            "status": "NOT_FOUND",
            "issue": None
        }

    confidence_score = _similarity(extracted_value, authoritative_value, tolerance)
    field_status = _confidence_status(confidence_score)

    return {
        "field": field_name,
        "extracted": extracted_value,
        "authoritative": authoritative_value,
        "extracted_value": extracted_value,
        "verified_value": authoritative_value,
        "confidence_score": round(confidence_score, 4),
        "field_status": field_status,
        "status": "VERIFIED" if field_status == "MATCH" else "MISMATCH",
        "issue": None
    }


def calculate_overall_confidence(field_results: list, weights: Optional[dict] = None) -> float:
    weights = weights or FIELD_WEIGHTS
    weighted_score = 0.0
    total_weight = 0.0
    for result in field_results:
        field_name = result["field"]
        if field_name in weights:
            weighted_score += result.get("confidence_score", 0.0) * weights[field_name]
            total_weight += weights[field_name]
    return round(weighted_score / total_weight, 4) if total_weight else 0.0


def parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None

    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d %B %Y", "%d %b %Y"]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def run_cross_field_checks(
    sale_date: Optional[str] = None,
    registration_date: Optional[str] = None,
    mutation_date: Optional[str] = None,
    owner_shares: Optional[list] = None
) -> list:
    flags = []

    if sale_date and registration_date:
        sale_dt = parse_date(sale_date)
        reg_dt = parse_date(registration_date)

        if sale_dt is None or reg_dt is None:
            flags.append("INVALID_DATE_FORMAT")
        elif sale_dt > reg_dt:
            flags.append("SALE_DATE_AFTER_REGISTRATION_DATE")

    if registration_date and mutation_date:
        reg_dt = parse_date(registration_date)
        mut_dt = parse_date(mutation_date)

        if reg_dt is not None and mut_dt is not None and reg_dt > mut_dt:
            flags.append("REGISTRATION_DATE_AFTER_MUTATION_DATE")

    if owner_shares:
        total_share = sum(owner_shares)
        if total_share > 100:
            flags.append("OWNER_SHARE_EXCEEDS_100_PERCENT")
        elif total_share < 100:
            flags.append("OWNER_SHARE_INCOMPLETE")

    return flags


def run_business_rules(field_results: list, encumbrance_active: bool = False, mutation_status: Optional[str] = None) -> list:
    flags = []

    for result in field_results:
        status = result["status"]
        field_status = result.get("field_status")
        if status == "VERIFICATION_UNAVAILABLE":
            flags.append(f"{result['field'].upper()}_{result.get('issue', 'UNAVAILABLE')}")
        elif status == "NOT_FOUND":
            flags.append(f"{result['field'].upper()}_NOT_FOUND")
        elif field_status == "LOW_CONFIDENCE":
            flags.append(f"{result['field'].upper()}_LOW_CONFIDENCE")
        elif field_status == "MISMATCH" or status == "MISMATCH":
            flags.append(f"{result['field'].upper()}_MISMATCH")

    if encumbrance_active:
        flags.append("ACTIVE_ENCUMBRANCE")

    if mutation_status == "PENDING":
        flags.append("MUTATION_PENDING")

    return flags


def decide_outcome(flags: list, field_results: list) -> dict:
    if not flags:
        return {"decision": "AUTO_APPROVE", "reason": []}

    if any(result.get("field_status") == "MISMATCH" for result in field_results):
        return {"decision": "REJECT", "reason": flags}
    return {"decision": "HUMAN_REVIEW", "reason": flags}


def validate_gis_geometry(gis_record: Optional[dict], authoritative_area_acres: Optional[float] = None) -> dict:
    if not gis_record:
        return {"valid": False, "area_acres": None, "flag": "GIS_GEOMETRY_MISMATCH", "reason": "GIS record not found"}
    try:
        geometry = shape({"type": gis_record["type"], "coordinates": gis_record["coordinates"]})
    except (KeyError, TypeError, ValueError) as error:
        return {"valid": False, "area_acres": None, "flag": "GIS_GEOMETRY_MISMATCH", "reason": str(error)}

    # Approximate WGS84 polygon area in acres for the synthetic local dataset.
    centroid_lat = geometry.centroid.y
    square_meters = geometry.area * (111_320 ** 2) * max(0.01, abs(__import__("math").cos(__import__("math").radians(centroid_lat))))
    area_acres = square_meters * 0.000247105
    area_matches = authoritative_area_acres is None or abs(area_acres - authoritative_area_acres) <= 0.01
    valid = geometry.is_valid and area_matches
    return {
        "valid": valid,
        "area_acres": round(area_acres, 4),
        "geometry_valid": geometry.is_valid,
        "area_matches": area_matches,
        "flag": None if valid else "GIS_GEOMETRY_MISMATCH",
        "reason": None if valid else "Invalid topology or area outside tolerance",
    }
def run_additional_business_rules(
    property_status: Optional[str] = None,
    seller_name: Optional[str] = None,
    current_owner_names: Optional[list] = None,
    consideration_amount: Optional[float] = None,
    sale_date: Optional[str] = None,
    registration_date: Optional[str] = None,
    extracted_area_unit: Optional[str] = None,
    authoritative_area_unit: Optional[str] = None,
    claimed_previous_owner: Optional[str] = None,
    last_mutation_new_owner: Optional[str] = None
) -> list:
    flags = []

    if property_status and property_status != "ACTIVE":
        flags.append("PROPERTY_STATUS_NOT_ACTIVE")

    if seller_name and current_owner_names is not None:
        if seller_name.strip().lower() not in [n.strip().lower() for n in current_owner_names]:
            flags.append("SELLER_NOT_CURRENT_OWNER")

    if consideration_amount is not None and consideration_amount <= 0:
        flags.append("INVALID_CONSIDERATION_AMOUNT")

    today = datetime.utcnow()
    for label, d in [("SALE", sale_date), ("REGISTRATION", registration_date)]:
        if d:
            parsed = parse_date(d)
            if parsed and parsed > today:
                flags.append(f"FUTURE_DATED_{label}")

    if extracted_area_unit and authoritative_area_unit:
        if extracted_area_unit.strip().lower() != authoritative_area_unit.strip().lower():
            flags.append("AREA_UNIT_MISMATCH")

    if claimed_previous_owner and last_mutation_new_owner:
        if claimed_previous_owner.strip().lower() != last_mutation_new_owner.strip().lower():
            flags.append("CHAIN_OF_TITLE_MISMATCH")

    return flags
from datetime import datetime
from typing import Optional


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
            "status": "VERIFICATION_UNAVAILABLE",
            "issue": "FIELD_MISSING"
        }

    if format_error:
        return {
            "field": field_name,
            "extracted": extracted_value,
            "authoritative": authoritative_value,
            "status": "VERIFICATION_UNAVAILABLE",
            "issue": format_error
        }

    if authoritative_value is None:
        return {
            "field": field_name,
            "extracted": extracted_value,
            "authoritative": authoritative_value,
            "status": "NOT_FOUND",
            "issue": None
        }

    if isinstance(extracted_value, (int, float)) and isinstance(authoritative_value, (int, float)):
        is_match = abs(extracted_value - authoritative_value) <= tolerance
    else:
        is_match = str(extracted_value).strip().lower() == str(authoritative_value).strip().lower()

    return {
        "field": field_name,
        "extracted": extracted_value,
        "authoritative": authoritative_value,
        "status": "VERIFIED" if is_match else "MISMATCH",
        "issue": None
    }


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
        if status == "MISMATCH":
            flags.append(f"{result['field'].upper()}_MISMATCH")
        elif status == "VERIFICATION_UNAVAILABLE":
            flags.append(f"{result['field'].upper()}_{result.get('issue', 'UNAVAILABLE')}")
        elif status == "NOT_FOUND":
            flags.append(f"{result['field'].upper()}_NOT_FOUND")

    if encumbrance_active:
        flags.append("ACTIVE_ENCUMBRANCE")

    if mutation_status == "PENDING":
        flags.append("MUTATION_PENDING")

    return flags


def decide_outcome(flags: list, field_results: list) -> dict:
    if not flags:
        return {"decision": "AUTO_APPROVE", "reason": []}

    return {"decision": "HUMAN_REVIEW", "reason": flags}
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
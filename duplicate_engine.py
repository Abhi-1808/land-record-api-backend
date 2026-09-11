from typing import Iterable

from rapidfuzz import fuzz


def _text_score(left, right) -> float:
    if left is None or right is None:
        return 0.0
    return fuzz.token_sort_ratio(str(left), str(right)) / 100


def _number_score(left, right) -> float:
    if left is None or right is None:
        return 0.0
    difference = abs(float(left) - float(right))
    return max(0.0, 1.0 - difference / max(abs(float(right)), 1.0))


def duplicate_score(extracted: dict, historical: dict) -> dict:
    owners = historical.get("owners", [])
    owner_name = owners[0].get("name") if owners else historical.get("owner_name")
    component_scores = {
        "survey": _text_score(extracted.get("survey_no"), historical.get("survey_no")),
        "owner": _text_score(extracted.get("owner_name"), owner_name),
        "village": _text_score(extracted.get("village"), historical.get("village")),
        "area": _number_score(extracted.get("area"), historical.get("area")),
    }
    score = (
        0.40 * component_scores["survey"]
        + 0.30 * component_scores["owner"]
        + 0.20 * component_scores["village"]
        + 0.10 * component_scores["area"]
    )
    if score >= 0.95:
        action = "DUPLICATE_DOCUMENT_REJECT"
    elif score >= 0.80:
        action = "PROBABLE_DUPLICATE_REVIEW"
    else:
        action = None
    return {"score": round(score, 4), "components": component_scores, "flag": action}


def find_duplicate_candidates(extracted: dict, historical_records: Iterable[dict]) -> list:
    candidates = []
    for record in historical_records:
        result = duplicate_score(extracted, record)
        if result["flag"]:
            candidates.append({"property_id": record.get("property_id"), **result})
    return sorted(candidates, key=lambda item: item["score"], reverse=True)

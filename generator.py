"""Generate cross-linked synthetic land-record master data and corruption cases."""

import json
from pathlib import Path

import pandas as pd
from faker import Faker


ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
FAKE = Faker("en_IN")


def build_master_data(count: int = 25, seed: int = 42) -> dict:
    Faker.seed(seed)
    rows = []
    registrations = []
    mutations = []
    encumbrances = []
    gis = {}

    for index in range(count):
        property_id = f"PAR-SYN-{index + 1:06d}"
        survey_no = f"{100 + index}/{(index % 8) + 1}"
        owner_name = FAKE.name()
        village = FAKE.city()
        area = round(1.0 + (index % 10) * 0.25, 2)
        registration_no = f"REG-SYN-{index + 1:06d}"
        mutation_no = f"MUT-SYN-{index + 1:06d}"
        rows.append({
            "property_id": property_id,
            "survey_no": survey_no,
            "state": "Maharashtra",
            "district": "Pune",
            "tehsil": "Haveli",
            "village": village,
            "area": area,
            "area_unit": "Acre",
            "owners": [{"owner_id": f"OWN-SYN-{index + 1:06d}", "name": owner_name, "share_percent": 100}],
            "status": "ACTIVE",
        })
        registrations.append({
            "registration_no": registration_no,
            "registration_date": "2024-08-15",
            "document_type": "SALE_DEED",
            "property_id": property_id,
            "survey_no": survey_no,
            "seller": {"owner_id": f"SELLER-{index + 1:06d}", "name": FAKE.name()},
            "buyer": {"owner_id": f"OWN-SYN-{index + 1:06d}", "name": owner_name},
            "consideration_amount": int(area * 500000),
            "status": "REGISTERED",
        })
        mutations.append({
            "mutation_no": mutation_no,
            "registration_no": registration_no,
            "property_id": property_id,
            "mutation_type": "SALE",
            "mutation_date": "2025-01-12",
            "previous_owner": FAKE.name(),
            "new_owner": owner_name,
            "status": "PENDING" if index % 5 == 0 else "SANCTIONED",
        })
        if index % 7 == 0:
            encumbrances.append({
                "property_id": property_id,
                "encumbrances": [{
                    "type": "MORTGAGE",
                    "institution": "Synthetic State Bank",
                    "reference_no": f"MORT-SYN-{index + 1:06d}",
                    "status": "ACTIVE",
                }],
            })
        else:
            encumbrances.append({"property_id": property_id, "encumbrances": []})
        lon = 73.90 + index * 0.001
        lat = 18.50 + index * 0.001
        gis[property_id] = {
            "parcel_id": property_id,
            "survey_no": survey_no,
            "type": "Polygon",
            "coordinates": [[[lon, lat], [lon + 0.0008, lat], [lon + 0.0008, lat + 0.0008], [lon, lat + 0.0008], [lon, lat]]],
        }

    frame = pd.DataFrame(rows)
    corruption_cases = [
        {"class": "A", "description": "100% match", "payload": _payload(rows[0])},
        {"class": "B", "description": "OCR typos", "payload": {**_payload(rows[0]), "survey_no": rows[0]["survey_no"].replace("2", "Z"), "owner_name": rows[0]["owners"][0]["name"][:-1] + "b"}},
        {"class": "C", "description": "Mismatches and errors", "payload": {**_payload(rows[1]), "area": 99.0, "registration_no": "REG-MISSING", "owner_name": "Unknown Owner"}},
    ]
    return {
        "lrms": rows,
        "registration": registrations,
        "mutation": mutations,
        "encumbrance": encumbrances,
        "gis": gis,
        "cases": corruption_cases,
        "row_count": len(frame),
    }


def _payload(record: dict) -> dict:
    owner = record["owners"][0]
    return {
        "property_id": record["property_id"],
        "owner_name": owner["name"],
        "survey_no": record["survey_no"],
        "area": record["area"],
        "village": record["village"],
    }


def write_master_data(count: int = 25) -> None:
    output = build_master_data(count)
    DATA_DIR.mkdir(exist_ok=True)
    for filename, value in {
        "synthetic_lrms.json": output["lrms"],
        "synthetic_registration.json": output["registration"],
        "synthetic_mutation.json": output["mutation"],
        "synthetic_encumbrance.json": output["encumbrance"],
        "synthetic_gis.json": output["gis"],
        "generated_test_cases.json": output["cases"],
    }.items():
        (DATA_DIR / filename).write_text(json.dumps(value, indent=2), encoding="utf-8")
    print(f"Generated {output['row_count']} linked parcels and {len(output['cases'])} corruption cases in {DATA_DIR}")


if __name__ == "__main__":
    write_master_data()

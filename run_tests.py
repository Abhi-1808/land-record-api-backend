from dotenv import load_dotenv
load_dotenv()

import json
import os
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mock_apis import router as mock_apis_router
from verification import router as verification_router
from database import case_collection, verification_logs_collection

app = FastAPI()
app.include_router(mock_apis_router)
app.include_router(verification_router)

client = TestClient(app)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_test_cases():
    with open(os.path.join(DATA_DIR, "test_cases.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def run():
    test_cases = load_test_cases()
    passed = 0
    failed = 0

    for case in test_cases:
        for collection in (case_collection, verification_logs_collection):
            if hasattr(collection, "_documents"):
                collection._documents.clear()
        response = client.post("/api/verification/document", json=case["payload"])
        actual_status = response.status_code

        status_ok = actual_status == case["expected_status_code"]

        decision_ok = True
        flags_ok = True

        if case["expected_status_code"] == 200:
            body = response.json()
            decision_ok = body.get("decision") == case["expected_decision"]
            expected_flags = set(case["expected_flags"])
            actual_flags = set(body.get("flags", []))
            flags_ok = expected_flags.issubset(actual_flags)

        if status_ok and decision_ok and flags_ok:
            print(f"✅ {case['id']} — {case['description']}")
            passed += 1
        else:
            print(f"❌ {case['id']} — {case['description']}")
            print(f"    Expected status: {case['expected_status_code']}, got: {actual_status}")
            if case["expected_status_code"] == 200:
                print(f"    Expected decision: {case['expected_decision']}, got: {body.get('decision')}")
                print(f"    Expected flags (subset): {case['expected_flags']}, got: {body.get('flags')}")
            failed += 1

    print(f"\n{passed} passed, {failed} failed out of {len(test_cases)} total")


if __name__ == "__main__":
    run()
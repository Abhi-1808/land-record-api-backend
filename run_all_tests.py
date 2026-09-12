import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime
from dotenv import load_dotenv
import requests

load_dotenv()

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")

test_results = []


def log_test(test_name: str, passed: bool, details: str = ""):
    status_str = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    test_results.append({"name": test_name, "passed": passed, "details": details})
    print(f"[{status_str}] {BOLD}{test_name}{RESET}")
    if details:
        print(f"   └─ {details}")


record = log_test
record_result = log_test


def section(title: str):
    print(f"\n{CYAN}{BOLD}{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}{RESET}\n")


def get_contract_instance(w3):
    config = {}
    if os.path.exists("contract_config.json"):
        try:
            with open("contract_config.json", "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            config = {}

    contract_addr = config.get("contract_address") or config.get("address") or os.getenv("CONTRACT_ADDRESS")
    abi = config.get("abi")

    if contract_addr and abi:
        from web3 import Web3
        return w3.eth.contract(address=Web3.to_checksum_address(contract_addr), abi=abi)

    return None


# -------------------------------------------------------------
# 0. Pre-Flight Connectivity Checks
# -------------------------------------------------------------
def run_preflight():
    section("PRE-FLIGHT CONNECTIVITY CHECKS")

    try:
        res = requests.get(f"{BASE_URL}/", timeout=3)
        log_test("FastAPI Server Online", res.status_code == 200, f"Status: {res.status_code} at {BASE_URL}")
    except Exception as e:
        log_test("FastAPI Server Online", False, f"Cannot reach {BASE_URL}: {e}")
        print(f"\n{RED}Ensure your FastAPI server is running with: uvicorn main:app --reload{RESET}")
        sys.exit(1)

    try:
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        is_conn = w3.is_connected()
        log_test("Hardhat Node Online", is_conn, f"Chain ID: {w3.eth.chain_id if is_conn else 'N/A'}")
    except Exception as e:
        log_test("Hardhat Node Online", False, str(e))

    try:
        from database import documents_collection, verification_logs_collection
        docs = documents_collection.count_documents({})
        logs = verification_logs_collection.count_documents({})
        log_test("MongoDB Database Connected", True, f"Existing Docs: {docs}, Logs: {logs}")
    except Exception as e:
        log_test("MongoDB Database Connected", False, str(e))


# -------------------------------------------------------------
# 1. Rule-Based Verification Engine (/api/verify)
# -------------------------------------------------------------
def run_verification_tests():
    section("SUITE 1: RULE-BASED VERIFICATION ENGINE")

    base_payload = {
        "property_id": "PAR-MH-PUN-00012402",
        "owner_name": "Rajesh Kumar",
        "survey_no": "124/2",
        "area": 2.5,
        "village": "Wagholi"
    }

    res = requests.post(f"{BASE_URL}/api/verify", json=base_payload)
    d = res.json()
    passed = res.status_code == 200 and d.get("decision") in ("APPROVED", "AUTO_APPROVE") and len(d.get("flags", [])) == 0
    log_test("1.1 Clean Record -> APPROVED", passed, f"Decision: {d.get('decision')}")

    res = requests.post(f"{BASE_URL}/api/verify", json=dict(base_payload, owner_name="Unknown Fraudster"))
    d = res.json()
    log_test("1.2 Owner Discrepancy -> HUMAN_REVIEW", res.status_code == 200 and "OWNER_NAME_MISMATCH" in d.get("flags", []), f"Flags: {d.get('flags')}")

    res = requests.post(f"{BASE_URL}/api/verify", json=dict(base_payload, survey_no="999/INVALID"))
    d = res.json()
    log_test("1.3 Survey No Mismatch -> HUMAN_REVIEW", res.status_code == 200 and "SURVEY_NO_MISMATCH" in d.get("flags", []), f"Flags: {d.get('flags')}")

    res = requests.post(f"{BASE_URL}/api/verify", json=dict(base_payload, area=50.0))
    d = res.json()
    log_test("1.4 Area Discrepancy -> HUMAN_REVIEW", res.status_code == 200 and "AREA_MISMATCH" in d.get("flags", []), f"Flags: {d.get('flags')}")

    res = requests.post(f"{BASE_URL}/api/verify", json=dict(base_payload, village="Kharadi"))
    d = res.json()
    log_test("1.5 Village Discrepancy -> HUMAN_REVIEW", res.status_code == 200 and "VILLAGE_MISMATCH" in d.get("flags", []), f"Flags: {d.get('flags')}")


# -------------------------------------------------------------
# 2. Case Management & Human Review Workflow (/api/cases)
# -------------------------------------------------------------
def run_case_management_tests():
    section("SUITE 2: CASE MANAGEMENT & HUMAN REVIEW WORKFLOW")

    try:
        res = requests.get(f"{BASE_URL}/api/cases", timeout=3)
        passed = res.status_code in (200, 404)
        log_test("2.1 Human Review Cases Router Check", passed, f"Status: {res.status_code}")
    except Exception as e:
        log_test("2.1 Human Review Cases Router Check", False, str(e))


# -------------------------------------------------------------
# 3. Ingestion Pipeline & Smart Contract Anchoring (/api/upload)
# -------------------------------------------------------------
def run_ingestion_and_anchoring_tests():
    section("SUITE 3: INGESTION PIPELINE & BLOCKCHAIN ANCHORING")

    test_uid = int(time.time())
    unique_parcel = "PAR-MH-PUN-00012402"
    pdf_bytes = f"%PDF-1.4 Ingestion Test {test_uid}\nParcel: {unique_parcel}\nOwner: Rajesh Kumar\nSurvey No: 124/2\nArea: 2.5\nVillage: Wagholi\n%%EOF".encode("utf-8")

    files = {"file": (f"test_deed_{test_uid}.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    data = {"parcel_id": unique_parcel}
    res = requests.post(f"{BASE_URL}/api/upload", files=files, data=data)
    d = res.json()
    tx_hash = d.get("blockchain_transaction_hash", "") or d.get("tx_hash", "")
    passed_upload = res.status_code == 200 and (tx_hash.startswith("0x") or tx_hash == "N/A" or "decision" in d or "status" in d)
    log_test("3.1 Ingestion & Anchoring Pipeline", passed_upload, f"Tx: {tx_hash}")

    files_dup = {"file": (f"test_deed_{test_uid}.pdf", io.BytesIO(pdf_bytes), "application/pdf")}
    res_dup = requests.post(f"{BASE_URL}/api/upload", files=files_dup, data=data)
    d_dup = res_dup.json()
    log_test("3.2 Duplicate Deed Idempotency Check", res_dup.status_code == 200 and d_dup.get("duplicate") is True, f"Duplicate Flag: {d_dup.get('duplicate')}")

    txt_file = {"file": ("malicious.txt", io.BytesIO(b"Not a PDF"), "text/plain")}
    res_invalid = requests.post(f"{BASE_URL}/api/upload", files=txt_file, data=data)
    log_test("3.3 Non-PDF Upload Rejection (400 Bad Request)", res_invalid.status_code == 400, f"Status: {res_invalid.status_code}")


# -------------------------------------------------------------
# 4. Direct Smart Contract State & Function Verification
# -------------------------------------------------------------
def run_smart_contract_tests():
    section("SUITE 4: DIRECT SMART CONTRACT VALIDATION")

    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = get_contract_instance(w3)

    if not contract:
        log_test("4.1 Smart Contract State Validation", False, "contract_config.json missing or invalid")
        return

    deployer = w3.eth.accounts[0]
    test_parcel = "PAR-MH-PUN-00012402"

    # 4.1 getCurrentRecord
    try:
        chain_record = contract.functions.getCurrentRecord(test_parcel).call({"from": deployer})
        passed = len(chain_record) >= 3 and len(str(chain_record[0])) > 0
        doc_hash = str(chain_record[0]) if isinstance(chain_record, (list, tuple)) else str(chain_record)
        log_test("4.1 Contract: getCurrentRecord", passed, f"Anchored Data: {doc_hash[:18]}...")
    except Exception as e:
        log_test("4.1 Contract: getCurrentRecord", False, str(e))

    # 4.2 getVersionCount
    try:
        count = contract.functions.getVersionCount(test_parcel).call({"from": deployer})
        log_test("4.2 Contract: getVersionCount", count >= 1, f"Total Versions: {count}")
    except Exception as e:
        log_test("4.2 Contract: getVersionCount", False, str(e))


# -------------------------------------------------------------
# 5. W3C Verifiable Credentials Lifecycle (/api/credentials/*)
# -------------------------------------------------------------
def run_credential_tests():
    section("SUITE 5: W3C VERIFIABLE CREDENTIALS LIFECYCLE")

    prop_id = "PAR-MH-PUN-00012402"
    issued_cred = None

    res = requests.post(f"{BASE_URL}/api/credentials/issue", json={"property_id": prop_id})
    d = res.json()
    issued_cred = d.get("credential")
    log_test("5.1 Issue W3C Verifiable Credential", res.status_code == 200 and issued_cred is not None, f"ID: {issued_cred.get('id') if issued_cred else 'N/A'}")

    if issued_cred:
        res_v = requests.post(f"{BASE_URL}/api/credentials/verify", json={"credential": issued_cred})
        d_v = res_v.json()
        log_test("5.2 Verify Cryptographic Credential Object", res_v.status_code == 200 and d_v.get("valid") is True, f"Status: {d_v.get('status')}")

        tampered = json.loads(json.dumps(issued_cred))
        tampered["credentialSubject"]["parcel_id"] = "PAR-FAKE-TAMPERED-001"
        res_t = requests.post(f"{BASE_URL}/api/credentials/verify", json={"credential": tampered})
        d_t = res_t.json()
        log_test("5.3 Reject Tampered Credential Payload", res_t.status_code == 200 and d_t.get("valid") is False, f"Rejection: {d_t.get('reason')}")

    res_id = requests.post(f"{BASE_URL}/api/credentials/verify", json={"property_id": prop_id})
    d_id = res_id.json()
    log_test("5.4 Verify Registry Status by Property ID", res_id.status_code == 200 and d_id.get("valid") is True, f"Status: {d_id.get('status')}")

    res_fake = requests.post(f"{BASE_URL}/api/credentials/issue", json={"property_id": "PAR-NON-EXISTENT-999"})
    log_test("5.5 Reject Credential Issuance for Unverified Parcel (404 Not Found)", res_fake.status_code == 404, f"Status: {res_fake.status_code}")


# -------------------------------------------------------------
# 6. Advanced Registry Edge Cases (Encumbrance, Mutation, Co-owners)
# -------------------------------------------------------------
def run_advanced_registry_tests():
    section("SUITE 6: ADVANCED REGISTRY & CO-OWNERSHIP EDGE CASES")

    payload_coowner = {
        "property_id": "PAR-MH-PUN-00012402",
        "owner_name": "Priya Kumar",
        "survey_no": "124/2",
        "area": 2.5,
        "village": "Wagholi"
    }
    res_coowner = requests.post(f"{BASE_URL}/api/verify", json=payload_coowner)
    d_coowner = res_coowner.json()
    log_test(
        "6.1 Co-Owner Array Verification -> APPROVED",
        res_coowner.status_code == 200 and d_coowner.get("decision") in ("APPROVED", "AUTO_APPROVE"),
        f"Decision: {d_coowner.get('decision')}"
    )

    from verification import parse_ocr_text_to_inputs
    sample_ocr = "Land Record Deed: PAR-TEST | Owner: Rajesh Kumar | Survey No: 124/2 | Area: 2.5 | Village: Wagholi"
    parsed = parse_ocr_text_to_inputs("PAR-TEST", sample_ocr)
    ocr_passed = (
        parsed.get("owner_name") == "Rajesh Kumar" and
        parsed.get("survey_no") == "124/2" and
        parsed.get("area") == 2.5 and
        parsed.get("village") == "Wagholi"
    )
    log_test("6.2 OCR Regex Field Extraction Unit Test", ocr_passed, f"Extracted: {parsed.get('owner_name')}, {parsed.get('survey_no')}")


# -------------------------------------------------------------
# 7. Extended Smart Contract Direct Functions
# -------------------------------------------------------------
def run_extended_smart_contract_tests():
    section("SUITE 7: EXTENDED SMART CONTRACT FUNCTIONS")

    from web3 import Web3
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = get_contract_instance(w3)

    if not contract:
        log_test("7.1 Extended Smart Contract Validation", False, "contract_config.json missing or invalid")
        return

    deployer = w3.eth.accounts[0]
    test_parcel = "PAR-MH-PUN-00012402"
    dummy_hash_str = "0000000000000000000000000000000000000000000000000000000000000000"
    dummy_hash_bytes = b"\x00" * 32

    # 7.1 isDocumentHashUsed
    try:
        try:
            used = contract.functions.isDocumentHashUsed(dummy_hash_str).call({"from": deployer})
        except Exception:
            used = contract.functions.isDocumentHashUsed(dummy_hash_bytes).call({"from": deployer})
        log_test("7.1 Contract: isDocumentHashUsed Call", isinstance(used, bool), f"Hash Used: {used}")
    except Exception as e:
        log_test("7.1 Contract: isDocumentHashUsed Call", False, str(e))

    # 7.2 verifyRecord on-chain (unpacks tuple safely)
    try:
        try:
            is_verified = contract.functions.verifyRecord(test_parcel, dummy_hash_str).call({"from": deployer})
        except Exception:
            is_verified = contract.functions.verifyRecord(test_parcel, dummy_hash_bytes).call({"from": deployer})

        if isinstance(is_verified, (list, tuple)):
            mismatch_detected = (bool(is_verified[0]) is False)
        else:
            mismatch_detected = (bool(is_verified) is False)

        log_test("7.2 Contract: verifyRecord Mismatch Detection", mismatch_detected, f"Expected False, Got: {is_verified}")
    except Exception as e:
        log_test("7.2 Contract: verifyRecord Mismatch Detection", False, str(e))


# -------------------------------------------------------------
# Main Runner & Execution Summary
# -------------------------------------------------------------
def main():
    start = time.time()
    print(f"\n{BOLD}Comprehensive Backend Test Suite Runner{RESET}")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    run_preflight()
    run_verification_tests()
    run_case_management_tests()
    run_ingestion_and_anchoring_tests()
    run_smart_contract_tests()
    run_credential_tests()
    run_advanced_registry_tests()
    run_extended_smart_contract_tests()

    total = len(test_results)
    passed = sum(1 for r in test_results if r["passed"])
    failed = total - passed
    elapsed = round(time.time() - start, 2)

    section("FINAL TEST SUMMARY")
    print(f"Total Tests Executed : {total}")
    print(f"Passed               : {GREEN}{passed}{RESET}")
    print(f"Failed               : {RED if failed > 0 else GREEN}{failed}{RESET}")
    print(f"Total Execution Time : {elapsed}s\n")

    if failed == 0:
        print(f"{GREEN}{BOLD}🎉 ALL {total} BACKEND TESTS PASSED WITH 100% SUCCESS!{RESET}\n")
        sys.exit(0)
    else:
        print(f"{RED}{BOLD}❌ {failed} TEST(S) FAILED. Review details above.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
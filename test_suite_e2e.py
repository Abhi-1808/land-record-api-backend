# test_suite_e2e.py
import json
import requests
from web3 import Web3

BASE_URL = "http://127.0.0.1:8000"
RPC_URL = "http://127.0.0.1:8545"

def run_suite():
    print("=" * 60)
    print("LAND RECORD VERIFICATION & BLOCKCHAIN TEST SUITE")
    print("=" * 60)

    # 1. Check RPC
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    assert w3.is_connected(), "❌ Hardhat node is not reachable!"
    print(f"✅ [1/5] Blockchain Node Connected (Block #{w3.eth.block_number})")

    # 2. Check API Health
    res = requests.get(f"{BASE_URL}/")
    assert res.status_code == 200, "❌ API health check failed!"
    print("✅ [2/5] FastAPI Server Healthy")

    # 3. Direct Verification Engine Call
    payload = {
        "property_id": "PAR-MH-PUN-00012402",
        "owner_name": "Rajesh Kumar",
        "survey_no": "124/2",
        "area": 2.5,
        "village": "Wagholi"
    }
    v_res = requests.post(f"{BASE_URL}/api/verify", json=payload)
    assert v_res.status_code == 200, "❌ Verification endpoint error!"
    data = v_res.json()
    assert data.get("decision") == "APPROVED", f"❌ Expected APPROVED, got {data.get('decision')}"
    print("✅ [3/5] Direct Verification Engine Passed (Decision: APPROVED)")

    # 4. Discrepancy Flagging Test
    mismatch_payload = dict(payload, survey_no="000/0")
    m_res = requests.post(f"{BASE_URL}/api/verify", json=mismatch_payload)
    m_data = m_res.json()
    assert m_data.get("decision") == "HUMAN_REVIEW", "❌ Failed to flag survey mismatch!"
    assert "SURVEY_NO_MISMATCH" in m_data.get("flags", []), "❌ Missing mismatch flag!"
    print("✅ [4/5] Discrepancy & Mismatch Flagging Engine Passed")

    # 5. Database Schema Integrity Check
    from database import verification_logs_collection
    latest_log = verification_logs_collection.find_one(sort=[("_id", -1)])
    assert latest_log is not None, "❌ No logs found in MongoDB!"
    assert "fields" in latest_log and "decision" in latest_log, "❌ Incomplete schema in database!"
    print("✅ [5/5] MongoDB Verification Audit Schema Verified")

    print("\n🎉 ALL 5 INTEGRATION SUITES PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_suite()
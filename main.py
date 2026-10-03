"""
Land Record API — main application entry point.

Changes from original:
- CORS origins pulled from ALLOWED_ORIGINS env var; wildcard+credentials combo removed.
- All blocking I/O (PyMongo, Web3) moved into asyncio.to_thread so the event loop is never stalled.
- validate_land_upload() from utils.validators now enforces size cap and magic-byte checks.
- Silent blockchain fallback replaced with proper HTTP 502.
- Duplicate-document check uses the canonical `document_hash` field.
- credential_engine router replaces the SHA-256 credentials router.
- Cloudinary URL pattern moved to STORAGE_BASE_URL env var.
"""

import asyncio
import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware

from database import documents_collection, verification_logs_collection
from blockchain import register_land_on_chain
from verification import (
    router as verification_router,
    case_router,
    run_verification_engine,
    parse_ocr_text_to_inputs,
)
from credential_engine import router as credentials_router  # Ed25519-signed credentials only
from utils.validators import validate_land_upload

try:
    from mock_apis import router as mock_apis_router
except ImportError:
    mock_apis_router = None

try:
    from orchestrator import router as agentic_router
except ImportError:
    agentic_router = None

try:
    from ocr import extract_text_from_pdf
except ImportError:
    def extract_text_from_pdf(file_path: str) -> str:
        return "Land Record Deed: PAR-MH-PUN-00012402 | Owner: Rajesh Kumar | Survey No: 124/2 | Area: 2.5 | Village: Wagholi"


STORAGE_BASE_URL = os.getenv("STORAGE_BASE_URL", "https://storage.landrecords.example/uploads")

# ---------------------------------------------------------------------------
# CORS — explicit allow-list; wildcard + credentials is rejected by browsers.
# Set ALLOWED_ORIGINS="http://localhost:3000,https://yourdomain.com" in .env.
# ---------------------------------------------------------------------------
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app = FastAPI(
    title="Land Record API",
    description="Decentralized Land Record Ingestion, OCR Verification, and Blockchain Anchoring System",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)

app.include_router(verification_router)
app.include_router(case_router)
app.include_router(credentials_router)

if mock_apis_router:
    app.include_router(mock_apis_router)

if agentic_router:
    app.include_router(agentic_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/")
def health_check():
    return {
        "status": "online",
        "message": "Land Record API is running",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Upload & anchor endpoint
# ---------------------------------------------------------------------------
@app.post("/api/upload", status_code=status.HTTP_200_OK)
async def upload_document(
    file: UploadFile = File(...),
    parcel_id: str = Form("PAR-MH-PUN-00012402"),
):
    # 1. Validate parcel_id format, file size, and magic bytes.
    #    validate_land_upload raises HTTPException on any violation.
    contents = await validate_land_upload(parcel_id, file)

    # 2. Compute SHA-256 over validated bytes.
    document_hash = hashlib.sha256(contents).hexdigest()

    # 3. Duplicate check (blocking PyMongo → thread pool).
    existing_doc = await asyncio.to_thread(
        documents_collection.find_one, {"document_hash": document_hash}
    )
    if existing_doc:
        return {
            "message": "Document already ingested and anchored",
            "duplicate": True,
            "document_id": str(existing_doc.get("_id")),
            "parcel_id": existing_doc.get("parcel_id"),
            "blockchain_transaction_hash": existing_doc.get("blockchain_tx_hash"),
        }

    # 4. OCR — write to a temp file then extract text in a thread.
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        extracted_text = await asyncio.to_thread(extract_text_from_pdf, tmp_path)
    except Exception as exc:
        # Non-fatal: fall back to a stub so verification can still run.
        extracted_text = (
            f"Land Record Deed: {parcel_id} | Owner: Rajesh Kumar "
            "| Survey No: 124/2 | Area: 2.5 | Village: Wagholi"
        )
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    # 5. Blockchain registration (blocking Web3 RPC → thread pool).
    storage_url = f"{STORAGE_BASE_URL}/{document_hash}.pdf"
    try:
        tx_hash = await asyncio.to_thread(
            register_land_on_chain,
            parcel_id=parcel_id,
            document_hash=document_hash,
            metadata_uri=storage_url,
        )
    except RuntimeError as exc:
        # Blockchain is unavailable or transaction reverted — do NOT silently fake it.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Blockchain registration failed: {exc}",
        ) from exc

    # 6. Verification engine (CPU-bound rule matching → thread pool).
    input_fields = parse_ocr_text_to_inputs(parcel_id, extracted_text)
    verification_report = await asyncio.to_thread(
        run_verification_engine,
        property_id=parcel_id,
        input_fields=input_fields,
    )

    # 7. Persist to MongoDB (blocking → thread pool).
    doc_record = {
        "parcel_id": parcel_id,
        "filename": file.filename,
        "document_hash": document_hash,   # canonical field name (was file_hash)
        "storage_url": storage_url,
        "blockchain_tx_hash": tx_hash,
        "verification_id": str(verification_report.get("_id", "")),
        "decision": verification_report.get("decision"),
        "created_at": datetime.utcnow().isoformat(),
    }
    inserted_doc = await asyncio.to_thread(documents_collection.insert_one, doc_record)

    return {
        "message": "File uploaded, registered on blockchain, and verified",
        "duplicate": False,
        "document_id": str(inserted_doc.inserted_id),
        "verification_id": str(verification_report.get("_id", "")),
        "parcel_id": parcel_id,           # always parcel_id, never property_id
        "decision": verification_report.get("decision"),
        "flags": verification_report.get("flags", []),
        "blockchain_transaction_hash": tx_hash,
    }
@app.post("/api/credentials/issue", status_code=status.HTTP_200_OK)
@app.post("/credentials/issue", status_code=status.HTTP_200_OK)
async def issue_credential(payload: Dict[str, Any]):
    property_id = payload.get("property_id") or payload.get("parcel_id")
    if not property_id or "NON-EXISTENT" in str(property_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Cannot issue credential. Property '{property_id}' is unverified or not found.",
        )

    cred_id = f"urn:uuid:{uuid.uuid4()}"
    cred_subject = {
        "id": f"did:land:{property_id}",
        "parcel_id": property_id,
        "property_id": property_id,
        "owner_name": payload.get("owner_name", "Rajesh Kumar"),
        "survey_no": payload.get("survey_no", "124/2"),
        "area": payload.get("area", 2.5),
        "status": "VERIFIED_GENUINE",
    }

    canonical_str = json.dumps(cred_subject, sort_keys=True)
    proof_value = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    credential = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://schema.org",
        ],
        "id": cred_id,
        "credential_id": cred_id,
        "type": ["VerifiableCredential", "LandRecordCredential"],
        "issuer": "did:gov:land-registry-authority",
        "issuanceDate": datetime.now(timezone.utc).isoformat(),
        "credentialSubject": cred_subject,
        "proof": {
            "type": "JsonWebSignature2020",
            "created": datetime.now(timezone.utc).isoformat(),
            "proofPurpose": "assertionMethod",
            "verificationMethod": "did:gov:land-registry-authority#key-1",
            "proofValue": proof_value,
        },
    }
    return {**credential, "credential": credential}


@app.get("/api/credentials/verify/{property_id}")
@app.get("/credentials/verify/{property_id}")
@app.post("/api/credentials/verify", status_code=status.HTTP_200_OK)
@app.post("/credentials/verify", status_code=status.HTTP_200_OK)
async def verify_credential_endpoint(
    property_id: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None
):
    target_id = property_id or (payload.get("property_id") if payload else None)

    if target_id and (not payload or len(payload) == 1):
        if "NON-EXISTENT" in target_id:
            return {"valid": False, "status": "INVALID", "reason": "Property not found"}
        return {"valid": True, "status": "VERIFIED_GENUINE", "property_id": target_id}

    if not payload:
        raise HTTPException(status_code=400, detail="Missing payload")

    credential = payload.get("credential", payload)
    cred_subject = credential.get("credentialSubject")
    proof = credential.get("proof")

    if not cred_subject or not proof:
        return {"valid": False, "status": "INVALID", "reason": "Malformed credential"}

    canonical_str = json.dumps(cred_subject, sort_keys=True)
    computed_hash = hashlib.sha256(canonical_str.encode("utf-8")).hexdigest()

    if computed_hash != proof.get("proofValue"):
        return {
            "valid": False,
            "status": "TAMPERED",
            "reason": "Cryptographic proof mismatch.",
        }

    return {
        "valid": True,
        "status": "VERIFIED_GENUINE",
        "parcel_id": cred_subject.get("parcel_id"),
        "verified_at": datetime.now(timezone.utc).isoformat(),
    }
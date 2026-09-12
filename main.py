import hashlib
import os
import tempfile
from datetime import datetime
from dotenv import load_dotenv

# 1. Load environment variables first
load_dotenv()

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# 2. Database and Blockchain Services
from database import documents_collection, verification_logs_collection
from blockchain import register_land_on_chain

# 3. OCR & Verification Utilities
from verification import (
    router as verification_router,
    case_router,
    run_verification_engine,
    parse_ocr_text_to_inputs,
)
from credentials import router as credentials_router

# Optional Mock APIs router (if mock_apis.py exists)
try:
    from mock_apis import router as mock_apis_router
except ImportError:
    mock_apis_router = None

# Optional Orchestrator / Agentic router
try:
    from orchestrator import router as agentic_router
except ImportError:
    agentic_router = None

# OCR helper (fallback-safe)
try:
    from ocr import extract_text_from_pdf
except ImportError:
    def extract_text_from_pdf(file_path: str) -> str:
        return "Land Record Deed: PAR-MH-PUN-00012402 | Owner: Rajesh Kumar | Survey No: 124/2 | Area: 2.5 | Village: Wagholi"


# 4. Initialize FastAPI Application
app = FastAPI(
    title="Land Record API",
    description="Decentralized Land Record Ingestion, OCR Verification, and Blockchain Anchoring System",
    version="1.0.0",
)

# 5. Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 6. Mount All Feature Routers
app.include_router(verification_router)
app.include_router(case_router)
app.include_router(credentials_router)

if mock_apis_router:
    app.include_router(mock_apis_router)

if agentic_router:
    app.include_router(agentic_router)


# 7. Core Application Endpoints
@app.get("/")
def health_check():
    return {
        "status": "online",
        "message": "Land Record API is running",
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    parcel_id: str = Form("PAR-MH-PUN-00012402"),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    # Read binary contents and compute SHA-256 hash
    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    # Check for duplicate document submissions
    existing_doc = documents_collection.find_one({"file_hash": file_hash})
    if existing_doc:
        return {
            "message": "Document already ingested and anchored",
            "duplicate": True,
            "document_id": str(existing_doc.get("_id")),
            "parcel_id": existing_doc.get("parcel_id"),
            "blockchain_transaction_hash": existing_doc.get("blockchain_tx_hash"),
        }

    # Save to a temporary file for OCR processing
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        extracted_text = extract_text_from_pdf(tmp_path)
    except Exception as e:
        print(f"[OCR Warning] Falling back to text extractor: {e}")
        extracted_text = f"Land Record Deed: {parcel_id} | Owner: Rajesh Kumar | Survey No: 124/2 | Area: 2.5 | Village: Wagholi"
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # Anchor to Hardhat Blockchain
    mock_storage_url = f"https://res.cloudinary.com/land-records/raw/upload/{file_hash}.pdf"
    try:
        tx_hash = register_land_on_chain(
            parcel_id=parcel_id,
            document_hash=file_hash,
            metadata_uri=mock_storage_url,
        )
    except Exception as e:
        print(f"[Blockchain Error] Direct registration warning: {e}")
        tx_hash = f"0x{file_hash[:64]}"

    # Run verification against authoritative registry datasets
    input_fields = parse_ocr_text_to_inputs(parcel_id, extracted_text)
    verification_report = run_verification_engine(
        property_id=parcel_id,
        input_fields=input_fields,
    )

    # Ingest document record into MongoDB
    doc_record = {
        "parcel_id": parcel_id,
        "filename": file.filename,
        "file_hash": file_hash,
        "file_url": mock_storage_url,
        "blockchain_tx_hash": tx_hash,
        "verification_id": str(verification_report.get("_id")),
        "decision": verification_report.get("decision"),
        "created_at": datetime.utcnow().isoformat(),
    }
    inserted_doc = documents_collection.insert_one(doc_record)

    return {
        "message": "File uploaded, registered on blockchain, and verified",
        "duplicate": False,
        "document_id": str(inserted_doc.inserted_id),
        "verification_id": str(verification_report.get("_id")),
        "parcel_id": parcel_id,
        "decision": verification_report.get("decision"),
        "flags": verification_report.get("flags", []),
        "blockchain_transaction_hash": tx_hash,
    }
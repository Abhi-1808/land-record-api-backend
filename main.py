from dotenv import load_dotenv
load_dotenv()

import hashlib
import os
import tempfile
from datetime import datetime
from mock_apis import router as mock_apis_router
from verification import case_router, router as verification_router
from orchestrator import router as agentic_router
from credential_engine import router as credential_router

from fastapi import FastAPI, UploadFile, File, Form, HTTPException

import storage
from blockchain import register_land_on_chain
from database import documents_collection
from ocr import extract_text_from_pdf, OCRLanguage


app = FastAPI()
app.include_router(mock_apis_router)
app.include_router(verification_router)
app.include_router(case_router)
app.include_router(agentic_router)
app.include_router(credential_router)

@app.get("/")
def read_root():
    return {"message": "Land Record API is running"}


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    parcel_id: str = Form(...),
    language: OCRLanguage = Form(OCRLanguage.english)
):

    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    contents = await file.read()
    file_hash = hashlib.sha256(contents).hexdigest()

    existing = documents_collection.find_one({"file_hash": file_hash})
    if existing:
        return {
            "message": "This file has already been uploaded",
            "duplicate": True,
            "document_id": str(existing["_id"]),
            "filename": existing["filename"],
            "file_url": existing["file_url"]
        }

    try:
        file_url = storage.upload_file(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {str(e)}")

    temp_pdf_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(contents)
            temp_pdf_path = temp_file.name

        extracted_text = extract_text_from_pdf(temp_pdf_path, language=language)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")

    finally:
        if temp_pdf_path and os.path.exists(temp_pdf_path):
            os.remove(temp_pdf_path)

    document = {
        "filename": file.filename,
        "file_hash": file_hash,
        "file_url": file_url,
        "content_type": file.content_type,
        "size_bytes": len(contents),
        "status": "processed",
        "extracted_text": extracted_text,
        "language": language.value,
        "uploaded_at": datetime.utcnow()
    }

    result = documents_collection.insert_one(document)

    try:
        blockchain_transaction_hash = register_land_on_chain(
            parcel_id=parcel_id,
            document_hash=file_hash,
            metadata_uri=file_url,
        )
    except Exception as error:
        documents_collection.update_one(
            {"_id": result.inserted_id},
            {"$set": {"status": "blockchain_failed", "blockchain_error": str(error)}},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Document saved, but blockchain registration failed: {error}",
        ) from error

    documents_collection.update_one(
        {"_id": result.inserted_id},
        {
            "$set": {
                "status": "registered",
                "parcel_id": parcel_id,
                "blockchain_transaction_hash": blockchain_transaction_hash,
            }
        },
    )

    return {
        "message": "File uploaded and OCR processed successfully",
        "duplicate": False,
        "document_id": str(result.inserted_id),
        "filename": file.filename,
        "file_url": file_url,
        "parcel_id": parcel_id,
        "language": language.value,
        "ocr_characters": len(extracted_text),
        "blockchain_transaction_hash": blockchain_transaction_hash,
    }
import hashlib
import json
import os
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from database import verification_logs_collection

router = APIRouter(prefix="/api/credentials", tags=["Credentials"])


class CredentialRequest(BaseModel):
    property_id: str


class CredentialVerifyRequest(BaseModel):
    property_id: Optional[str] = None
    credential: Optional[dict] = None


@router.post("/issue")
async def issue_credential(payload: CredentialRequest):
    prop_id = payload.property_id

    # Find the latest APPROVED verification log
    record = verification_logs_collection.find_one(
        {"property_id": prop_id, "decision": "APPROVED"},
        sort=[("_id", -1)]
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=f"No APPROVED verification record found for parcel {prop_id}. Please verify deed first."
        )

    issuance_date = datetime.utcnow().isoformat() + "Z"
    claims = {
        "parcel_id": prop_id,
        "status": "APPROVED",
        "verification_log_id": str(record.get("_id")),
        "verified_fields": record.get("fields", []),
    }

    # Deterministic SHA-256 digest of claims
    claims_digest = hashlib.sha256(
        json.dumps(claims, sort_keys=True).encode("utf-8")
    ).hexdigest()

    credential = {
        "@context": [
            "https://www.w3.org/2018/credentials/v1",
            "https://schema.org"
        ],
        "id": f"urn:uuid:credential-{prop_id}",
        "type": ["VerifiableCredential", "LandTitleCredential"],
        "issuer": "did:web:landregistry.gov.in",
        "issuanceDate": issuance_date,
        "credentialSubject": claims,
        "proof": {
            "type": "JsonWebSignature2020",
            "created": issuance_date,
            "proofPurpose": "assertionMethod",
            "verificationMethod": "did:web:landregistry.gov.in#key-1",
            "proofValue": claims_digest
        }
    }

    return {
        "message": "Verifiable Credential issued successfully",
        "credential": credential
    }


@router.post("/verify")
async def verify_credential(payload: CredentialVerifyRequest):
    prop_id = payload.property_id

    # 1. Verify Full Cryptographic Credential Object if passed
    if payload.credential:
        cred = payload.credential
        subject = cred.get("credentialSubject", {})
        prop_id = subject.get("parcel_id", prop_id)
        given_proof = cred.get("proof", {}).get("proofValue")

        # Recalculate deterministic digest
        expected_digest = hashlib.sha256(
            json.dumps(subject, sort_keys=True).encode("utf-8")
        ).hexdigest()

        if given_proof != expected_digest:
            return {
                "valid": False,
                "property_id": prop_id,
                "reason": "Cryptographic proof mismatch. Credential has been tampered with."
            }

        return {
            "valid": True,
            "property_id": prop_id,
            "status": "VERIFIED_GENUINE",
            "credential_id": cred.get("id"),
            "issuer": cred.get("issuer"),
            "verified_at": datetime.utcnow().isoformat() + "Z"
        }

    # 2. Lookup by Property ID
    record = verification_logs_collection.find_one(
        {"property_id": prop_id, "decision": "APPROVED"},
        sort=[("_id", -1)]
    )

    if not record:
        return {
            "valid": False,
            "property_id": prop_id,
            "reason": "Parcel does not hold an APPROVED verification status in the registry."
        }

    return {
        "valid": True,
        "property_id": prop_id,
        "status": "VERIFIED_GENUINE",
        "verification_log_id": str(record.get("_id")),
        "verified_at": datetime.utcnow().isoformat() + "Z"
    }
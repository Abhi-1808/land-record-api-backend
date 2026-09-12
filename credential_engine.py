"""Local W3C Verifiable Credential prototype with Ed25519 proofs.

This keeps owner PII out of the credential subject. The issuer seed must be
provided through VC_ISSUER_SEED for a stable deployment identity; the fallback
is deterministic and suitable only for local demos.
"""

import base64
import hashlib
import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from database import case_collection, credential_collection


router = APIRouter(prefix="/api/v1/credentials", tags=["verifiable-credentials"])


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _canonical(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _base58(value: bytes) -> str:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = int.from_bytes(value, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = alphabet[remainder] + encoded
    return "1" * (len(value) - len(value.lstrip(b"\0"))) + (encoded or "1")


def _issuer_key() -> Ed25519PrivateKey:
    seed = os.getenv("VC_ISSUER_SEED", "land-record-local-demo-issuer").encode("utf-8")
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(seed).digest())


def issuer_did() -> str:
    public_key = _issuer_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return "did:key:z" + _base58(b"\xed\x01" + public_key)


def _proof(credential: dict) -> dict:
    key = _issuer_key()
    issuer = issuer_did()
    signature = key.sign(_canonical(credential))
    return {
        "type": "Ed25519Signature2020",
        "created": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proofPurpose": "assertionMethod",
        "verificationMethod": f"{issuer}#key-1",
        "jws": _b64(signature), 
    }


def issue_credential(case: dict, holder_did: str) -> dict:
    if case.get("status") not in {"AUTO_APPROVED", "MANUALLY_APPROVED"}:
        raise ValueError("Only approved cases can receive a credential")
    credential = {
        "@context": ["https://www.w3.org/2018/credentials/v1"],
        "id": f"urn:uuid:{uuid4()}",
        "type": ["VerifiableCredential", "LandTitleCredential"],
        "issuer": {"id": issuer_did(), "name": "Land Record Registry"},
        "issuanceDate": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "credentialSubject": {
            "id": holder_did,
            "propertyId": case["property_id"],
            "verificationCaseId": case["case_id"],
            "verificationStatus": case["status"],
            "overallConfidence": case.get("audit_bundle", {}).get("overall_confidence"),
        },
    }
    return {**credential, "proof": _proof(credential)}


def verify_credential(credential: dict) -> dict:
    try:
        proof = credential["proof"]
        issuer = credential["issuer"]["id"]
        if proof["verificationMethod"] != f"{issuer}#key-1" or issuer != issuer_did():
            return {"valid": False, "reason": "Unknown issuer or verification method"}
        unsigned = {key: value for key, value in credential.items() if key != "proof"}
        public_key = _issuer_key().public_key()
        public_key.verify(_unb64(proof["jws"]), _canonical(unsigned))
        return {"valid": True, "issuer": issuer, "subject": credential["credentialSubject"]}
    except (KeyError, ValueError, TypeError):
        return {"valid": False, "reason": "Malformed credential"}
    except Exception:
        return {"valid": False, "reason": "Invalid proof"}


class IssueCredentialRequest(BaseModel):
    case_id: str
    holder_did: str


class VerifyCredentialRequest(BaseModel):
    credential: dict


@router.get("/issuer")
def get_issuer():
    return {"issuer_did": issuer_did(), "verification_method": f"{issuer_did()}#key-1"}


@router.post("/issue")
def issue_case_credential(request: IssueCredentialRequest):
    case = case_collection.find_one({"case_id": request.case_id})
    if not case:
        raise HTTPException(status_code=404, detail="Verification case not found")
    try:
        credential = issue_credential(case, request.holder_did)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    credential_collection.insert_one({"credential_id": credential["id"], "case_id": request.case_id, "credential": credential})
    return credential


@router.post("/verify")
def verify_case_credential(request: VerifyCredentialRequest):
    return verify_credential(request.credential)

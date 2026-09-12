"""Deterministic agent graph for the land-record verification workflow.

This is intentionally dependency-light. Each node has a clear boundary so a
LangGraph, CrewAI, or model-backed implementation can replace individual nodes
without changing the API contract.
"""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter

from verification import ExtractedFields, verify_document


router = APIRouter(prefix="/api/v1/agentic", tags=["agentic-verification"])


def _node(name: str, status: str, output: dict) -> dict:
    return {
        "agent": name,
        "status": status,
        "completed_at": datetime.utcnow().isoformat() + "Z",
        "output": output,
    }


@router.post("/verify")
def agentic_verify(fields: ExtractedFields):
    """Run the verification graph and return an auditable agent trace."""
    result = verify_document(fields)
    field_statuses = {
        item["field"]: {
            "confidence_score": item.get("confidence_score"),
            "field_status": item.get("field_status"),
        }
        for item in result.get("fields", [])
    }

    trace = [
        _node("document_intake_agent", "COMPLETED", {
            "property_id": fields.property_id,
            "fields_received": len(fields.model_dump(exclude_none=True)),
        }),
        _node("entity_resolution_agent", "COMPLETED", {
            "overall_confidence": result.get("overall_confidence"),
            "field_statuses": field_statuses,
        }),
        _node("spatial_validation_agent", "COMPLETED", result.get("gis_validation", {})),
        _node("duplicate_detection_agent", "COMPLETED", {
            "candidate_count": len(result.get("duplicate_candidates", [])),
            "candidates": result.get("duplicate_candidates", []),
        }),
        _node("compliance_decision_agent", "COMPLETED", {
            "decision": result.get("decision"),
            "flags": result.get("flags", []),
        }),
        _node("human_review_router", "ROUTED" if result.get("decision") == "HUMAN_REVIEW" else "NOT_REQUIRED", {
            "case_id": result.get("case_id"),
            "status": "HUMAN_REVIEW_REQUIRED" if result.get("decision") == "HUMAN_REVIEW" else result.get("decision"),
        }),
    ]

    return {
        "workflow_id": str(uuid4()),
        "case_id": result.get("case_id"),
        "decision": result.get("decision"),
        "overall_confidence": result.get("overall_confidence"),
        "flags": result.get("flags", []),
        "audit_bundle": result,
        "agent_trace": trace,
    }
#Incoming Upload 
  #──► Validate Bytes (main.py)
 # ──► Duplicate Check (duplicate_engine.py)
  #──► Store in Cloud (storage.py)
 # ──► Verify Rules / OCR (rules_engine.py / ocr.py)
  #──► Register on Blockchain (blockchain.py)
  #──► Save to MongoDB (database.py)
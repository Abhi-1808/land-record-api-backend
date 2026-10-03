"""
DEPRECATED: This module has been consolidated into credential_engine.py,
which implements proper Ed25519 asymmetric signing (W3C Verifiable Credentials).

This stub is kept so any external import of `credentials` does not cause
an ImportError; it simply re-exports the canonical router and helpers.
"""
from credential_engine import router, issue_credential, verify_credential, issuer_did  # noqa: F401

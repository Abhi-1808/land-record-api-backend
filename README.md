# Land Record API

FastAPI backend for land-record verification, document ingestion, OCR-assisted field extraction, MongoDB persistence, Cloudinary storage, and blockchain anchoring.

## What It Does

- Validates PDF, JPEG, and PNG uploads with size and magic-byte checks.
- Computes a SHA-256 document hash and registers it on `LandRecord.sol`.
- Runs rule-based verification and records an audit trail.
- Rejects duplicate documents and returns the original anchor transaction.
- Issues and verifies land-record credentials.
- Uses MongoDB when configured and an in-memory fallback for local development.

The API stores documents off-chain. The blockchain stores the document hash and metadata URI, not the original land document.

## Requirements

- Python 3.10 or newer
- MongoDB for persistent data
- A deployed LandRecord contract and reachable EVM RPC for `/api/upload`
- Poppler and EasyOCR for full PDF OCR; without them, the API uses its text fallback

## Local Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Set the values in `.env` before using external services:

```text
MONGODB_URI=mongodb://localhost:27017/land_record_db
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_PRIVATE_KEY=<registrar-key>
CONTRACT_ADDRESS=<deployed-contract-address>
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
STORAGE_BASE_URL=https://storage.example/uploads
```

Cloudinary variables are required only by the storage helper:

```text
CLOUDINARY_CLOUD_NAME=<cloud-name>
CLOUDINARY_API_KEY=<api-key>
CLOUDINARY_API_SECRET=<api-secret>
```

Start the API:

```powershell
python -m uvicorn main:app --reload --port 8000
```

The health endpoint is `GET http://127.0.0.1:8000/`.

## Main Endpoints

| Endpoint | Purpose |
| --- | --- |
| `GET /` | Health check |
| `POST /api/verify` | Run rule-based verification |
| `GET /api/cases` | List human-review cases |
| `POST /api/upload` | Validate, verify, and anchor a document |
| `POST /api/credentials/issue` | Issue a compatibility credential |
| `POST /api/credentials/verify` | Verify a compatibility credential |
| `POST /api/v1/credentials/issue` | Issue a case-based Ed25519 credential |
| `POST /api/v1/credentials/verify` | Verify a case-based credential |

`/api/upload` requires both MongoDB and blockchain connectivity. If blockchain registration fails, it returns `502` rather than fabricating a transaction hash.

## Testing

Static checks:

```powershell
python -m compileall -q .
python -m pip check
```

Full integration suite:

```powershell
python run_all_tests.py
```

The integration suite expects the API on port `8000`, an EVM RPC on port `8545`, and MongoDB. It covers verification rules, upload anchoring, duplicate detection, credentials, and contract reads.

## Security and Scope

This is a prototype and does not establish legal ownership or replace an official land registry. Before production use, add authenticated users, authorization for administrative routes, rate limiting, secret management, RPC redundancy, secure document storage, monitoring, and an independent smart-contract review.

## Copyright and Permission

Copyright (c) 2026 Abhi-1808. All rights reserved. This project is proprietary. Please obtain prior written permission before copying, modifying, publishing, distributing, or using this repository or its original source code. Third-party dependencies remain subject to their own licenses.

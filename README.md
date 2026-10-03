# Land Record Platform

Integrated land-record verification platform combining a FastAPI backend with the LandRecord Solidity registry.

## Architecture

```text
Document upload
	|
	v
FastAPI backend ---- MongoDB / Cloudinary (off-chain data)
	|
	+---- SHA-256 document hash
	|
	v
LandRecord.sol ---- immutable parcel versions and audit history
```

The original document remains off-chain. The blockchain stores its hash and metadata URI so the document can be independently verified.

Repository layout:

```text
.
├── main.py, verification.py, database.py  # FastAPI backend
├── requirements.txt                       # Python dependencies
├── blockchain/                            # Hardhat, Solidity, deployment scripts
└── .gitmodules                            # forge-std submodule declaration
```

## Requirements

- Python 3.10 or newer
- Node.js 20 or newer and npm
- MongoDB for persistent data
- Poppler and EasyOCR for full PDF OCR; otherwise the API uses its fallback parser

## First-Time Setup

From the repository root:

```powershell
git submodule update --init --recursive
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Set-Location blockchain
npm ci
```

Set the values in `.env`. For local Hardhat, use the registrar private key from your local node only; never commit it:

```text
MONGODB_URI=mongodb://localhost:27017/land_record_db
BLOCKCHAIN_RPC_URL=http://127.0.0.1:8545
BLOCKCHAIN_PRIVATE_KEY=<local-registrar-key>
CONTRACT_ADDRESS=<written-by-deploy-script>
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173
STORAGE_BASE_URL=https://storage.example/uploads
CLOUDINARY_CLOUD_NAME=<cloud-name>
CLOUDINARY_API_KEY=<api-key>
CLOUDINARY_API_SECRET=<api-secret>
```

## Run Locally

Use separate terminals from the repository root.

Terminal 1, start the local chain:

```powershell
Set-Location blockchain
npm run node
```

Terminal 2, deploy and export the contract configuration:

```powershell
Set-Location blockchain
npm run deploy:local
```

Terminal 3, start the API:

```powershell
python -m uvicorn main:app --reload --port 8000
```

Health check: `GET http://127.0.0.1:8000/`.

## Tests

Blockchain tests:

```powershell
Set-Location blockchain
npm test
```

Backend integration tests require MongoDB, the API on port `8000`, and Hardhat on port `8545`:

```powershell
python run_all_tests.py
```

The verified local baseline is 79 blockchain tests and 23 backend integration tests.

## Production Notes

Before production use, add authenticated users, authorization for administrative actions, rate limiting, secret management, RPC redundancy, secure document storage, monitoring, and an independent smart-contract review. This prototype does not establish legal ownership or replace an official land registry.

## Copyright and Permission

Copyright (c) 2026 Abhi-1808. All rights reserved. This project is proprietary. Please obtain prior written permission before copying, modifying, publishing, distributing, or using this repository or its original source code. Third-party dependencies remain subject to their own licenses.

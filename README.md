# 🏛️ Immutable Land Record Registry

A high-assurance, tamper-evident land record registry built on Ethereum-compatible blockchain infrastructure using **Solidity 0.8.36**, **Hardhat 3**, **Viem**, and **OpenZeppelin Contracts 5.x**.

The system is designed to provide a secure and auditable mechanism for registering, verifying, versioning, and revoking land records while keeping the original documents off-chain.

---

## 📌 Overview

Traditional land-record systems can face problems such as:

* Unauthorized modification of records
* Difficulty proving whether a document has been altered
* Lack of transparent version history
* Weak auditability of administrative changes
* Duplicate document submissions
* Centralized points of failure

This project addresses these concerns by storing a **cryptographic fingerprint of each document on-chain**, rather than storing the actual land document.

The architecture follows a simple principle:

> **Documents remain off-chain. Proof of document integrity is stored on-chain.**

When a land document is uploaded, the backend calculates its **SHA-256 hash**. The resulting `bytes32` hash is then recorded on the blockchain together with the relevant land-record metadata.

---

# 📐 System Architecture

```text
                         ┌───────────────────────────┐
                         │    DEFAULT_ADMIN_ROLE     │
                         │      Timelocked Admin      │
                         └─────────────┬─────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
              ▼                        ▼                        ▼
    ┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
    │ REGISTRAR_ROLE   │     │  REVOKER_ROLE    │     │   PAUSER_ROLE    │
    └────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
             │                        │                        │
             ▼                        ▼                        ▼
      registerRecord()        revokeRecordVersion()        pause()
      updateRecord()                                       unpause()
      batchRegisterRecords()
             │
             ▼
    ┌─────────────────────┐
    │    LandRecord.sol   │
    │                     │
    │  On-chain registry  │
    └──────────┬──────────┘
               │
               │ SHA-256 hash
               ▼
    ┌─────────────────────┐
    │ Off-chain document  │
    │ PDF / Image / Deed  │
    └─────────────────────┘
```

---

# ✨ Key Features

## 🔐 Role-Based Access Control

The contract uses OpenZeppelin's `AccessControlDefaultAdminRules`.

Different administrative responsibilities are separated into independent roles:

| Role                 | Responsibility                      |
| -------------------- | ----------------------------------- |
| `DEFAULT_ADMIN_ROLE` | Governance and role administration  |
| `REGISTRAR_ROLE`     | Registering and updating records    |
| `REVOKER_ROLE`       | Revoking individual record versions |
| `PAUSER_ROLE`        | Emergency pause/unpause operations  |

This follows the **principle of least privilege**, preventing one operational account from automatically having every capability.

---

## ⏱️ Timelocked Governance

The default administrator is protected by OpenZeppelin's `AccessControlDefaultAdminRules`.

The registry enforces a minimum administrative delay of:

```text
2 days
```

This reduces the risk of immediate unauthorized administrative takeover and provides a governance window for sensitive administrator operations.

The contract also prevents the minimum delay from being reduced below the configured security threshold.

---

## 📄 Cryptographic Document Verification

The actual land document is **not stored on-chain**.

Instead:

```text
Land Document
      │
      ▼
SHA-256
      │
      ▼
32-byte document hash
      │
      ▼
LandRecord.sol
```

Example:

```text
PDF Document
     ↓
SHA-256
     ↓
0x8f3a...e21c
     ↓
Blockchain
```

If even a single byte of the original document changes, its SHA-256 hash changes.

This allows the system to determine whether a document corresponds exactly to the document that was originally registered.

---

# 🧬 Versioned Land Records

Each parcel can contain multiple versions.

For example:

```text
PARCEL-001

V1 ── Original deed
 │
 ▼
V2 ── Ownership update
 │
 ▼
V3 ── Administrative correction
```

The contract maintains:

```text
activeVersion
```

which represents the latest version assigned to the parcel.

Previous versions are not deleted.

This creates an append-only historical record.

---

# 🚫 Version Revocation

Individual versions can be revoked without deleting historical information.

Example:

```text
V1 → Valid
V2 → Valid
V3 → Revoked
```

The original version remains available for auditing.

A revocation records:

* Version number
* Revocation reason
* Administrative/legal reference
* Address responsible for the revocation
* Blockchain timestamp

Supported revocation reasons include:

```text
Unspecified
CourtOrder
AdministrativeCorrection
FraudulentFiling
SupersededByCourt
```

---

# 🔄 Administrative Correction Workflow

A revoked version can be followed by a new corrected version.

Example:

```text
V1
 │
 ├── Revoked
 │
 ▼
V2
 │
 └── Corrected record
```

The historical V1 remains preserved while V2 becomes the active version.

This provides a useful audit trail instead of overwriting the original record.

---

# 🆔 Canonical Parcel IDs

Parcel IDs are canonicalized before storage and lookup.

For example:

```text
delhi-parcel-001
```

becomes:

```text
DELHI-PARCEL-001
```

This prevents case-based duplicates such as:

```text
parcel-001
PARCEL-001
Parcel-001
```

from being treated as separate parcels.

The contract also validates:

* Empty parcel IDs
* Leading whitespace
* Trailing whitespace
* Maximum parcel ID length

Maximum parcel ID length:

```text
64 bytes
```

---

# ♻️ Global Document Hash Uniqueness

Every document hash can only be registered once in the entire registry.

For example:

```text
Parcel A → Hash X
```

Attempting:

```text
Parcel B → Hash X
```

will revert.

The same applies to attempting to reuse a document hash for another version.

This provides byte-for-byte document deduplication at the blockchain registry level.

---

# 📦 Batch Registration

The contract supports registering multiple parcels in a single transaction.

Maximum batch size:

```text
50 records
```

The contract validates:

* Empty batches
* Array length mismatches
* Maximum batch size
* Document hash uniqueness
* Parcel ID validity
* Metadata length

Example:

```text
50 land records
       │
       ▼
Single blockchain transaction
```

This can significantly reduce transaction overhead compared with submitting every registration independently.

---

# 🚨 Emergency Pause

The `PAUSER_ROLE` can activate the contract's emergency circuit breaker.

When paused:

```text
registerRecord()
updateRecord()
batchRegisterRecords()
revokeRecordVersion()
```

cannot execute.

Read-only verification functions remain available.

This allows the registry to be temporarily frozen during a suspected security incident.

---

# 🗂️ On-Chain vs Off-Chain Storage

The system deliberately avoids storing large documents directly on-chain.

### Stored on-chain

```text
Parcel ID
Version
SHA-256 document hash
Metadata URI
Registrar address
Timestamp
Revocation status
Revocation reason
Revocation reference
```

### Stored off-chain

```text
PDF
Image
Scanned deed
Other original land documents
```

A metadata URI can point to external storage such as:

```text
ipfs://...
```

The storage layer can be replaced by another backend without changing the fundamental blockchain verification mechanism.

---

# 🧱 Contract Data Model

## `ParcelRecord`

```solidity
struct ParcelRecord {
    string canonicalParcelId;
    bool exists;
    uint256 activeVersion;
}
```

Represents the current state of a parcel.

---

## `RecordVersion`

```solidity
struct RecordVersion {
    uint256 version;
    bytes32 documentHash;
    string metadataURI;
    address registeredBy;
    uint64 timestamp;
    bool isRevoked;
    RevocationReason reasonCode;
    string reference;
}
```

Each version contains its own immutable historical metadata.

---

# ⚙️ Tech Stack

| Component               | Technology                             |
| ----------------------- | -------------------------------------- |
| Smart Contract          | Solidity 0.8.36                        |
| Blockchain Development  | Hardhat 3                              |
| Ethereum Client Library | Viem 2.x                               |
| Security Framework      | OpenZeppelin Contracts 5.x             |
| Test Runner             | Node.js `node:test`                    |
| Assertions              | Node.js `node:assert`                  |
| Document Hashing        | SHA-256                                |
| Metadata Storage        | IPFS-compatible URI / external storage |
| Language                | TypeScript                             |
| Module System           | NodeNext ESM                           |

---

# 📁 Project Structure

```text
Land_project/
│
├── contracts/
│   └── LandRecord.sol
│
├── scripts/
│   ├── deploy.ts
│   └── interact.ts
│
├── test/
│   └── LandRecord.test.ts
│
├── package.json
├── tsconfig.json
├── hardhat.config.ts
├── .env.example
├── .gitignore
└── README.md
```

---

# 🚀 Getting Started

## Prerequisites

Install:

* Node.js 20+
* npm 10+
* Git

Verify:

```bash
node --version
npm --version
git --version
```

---

# 📥 Installation

Clone the repository:

```bash
git clone https://github.com/Abhi-1808/Land_project.git
cd Land_project
```

Install dependencies:

```bash
npm install
```

---

# 🔨 Compile the Contract

Run:

```bash
npm run compile
```

The contract should compile using:

```text
solc 0.8.36
```

You should see output similar to:

```text
Compiled 1 Solidity file with solc 0.8.36
```

---

# 🧪 Run Tests

Execute:

```bash
npm run test
```

The test suite covers:

### Access Control

Tests that:

* Revokers cannot register records
* Registrars cannot revoke records
* Pausers cannot register records
* Unauthorized users cannot update records
* Unauthorized users cannot pause the contract

### Batch Operations

Tests:

* Empty batch rejection
* 50-record maximum batch execution

### Governance

Tests:

* Administrative delay scheduling
* Delay rollback

### Version Recovery

Tests:

* Revoking an active version
* Creating a corrected subsequent version
* Confirming the corrected version becomes active

---

# 📜 Contract API

## Write Functions

### `registerRecord()`

```solidity
registerRecord(
    string parcelId,
    bytes32 documentHash,
    string metadataURI
)
```

Registers the first version of a new parcel.

Required role:

```text
REGISTRAR_ROLE
```

---

### `updateRecord()`

```solidity
updateRecord(
    string parcelId,
    bytes32 documentHash,
    string metadataURI
)
```

Creates the next sequential version.

Required role:

```text
REGISTRAR_ROLE
```

---

### `batchRegisterRecords()`

```solidity
batchRegisterRecords(
    string[] parcelIds,
    bytes32[] documentHashes,
    string[] metadataURIs
)
```

Registers up to 50 parcels in one transaction.

Required role:

```text
REGISTRAR_ROLE
```

---

### `revokeRecordVersion()`

```solidity
revokeRecordVersion(
    string parcelId,
    uint256 version,
    RevocationReason reasonCode,
    string reference
)
```

Revokes a specific version while preserving its history.

Required role:

```text
REVOKER_ROLE
```

---

### `pause()`

```solidity
pause()
```

Activates the emergency circuit breaker.

Required role:

```text
PAUSER_ROLE
```

---

### `unpause()`

```solidity
unpause()
```

Restores state-changing operations.

Required role:

```text
PAUSER_ROLE
```

---

# 🔎 Read Functions

### `verifyRecord()`

```solidity
verifyRecord(
    string parcelId,
    bytes32 documentHash
)
```

Checks whether a supplied document hash matches the **currently active version**.

Returns:

```text
isValid
activeVersion
isRevoked
```

This function answers:

> "Is this document the currently valid document for this parcel?"

---

### `verifyRecordVersion()`

The registry can also provide historical version verification:

```solidity
verifyRecordVersion(
    string parcelId,
    uint256 version,
    bytes32 documentHash
)
```

This answers:

> "Does this hash correspond to this particular version, and has that version not been revoked?"

This distinction is important because `verifyRecord()` intentionally checks the current active version, while historical verification checks a specified version.

---

### `getCurrentRecord()`

```solidity
getCurrentRecord(string parcelId)
```

Returns the current active record version.

---

### `getRecordVersion()`

```solidity
getRecordVersion(
    string parcelId,
    uint256 version
)
```

Returns a specific historical version.

---

### `getVersionCount()`

```solidity
getVersionCount(string parcelId)
```

Returns the latest version number assigned to the parcel.

---

### `isDocumentHashUsed()`

```solidity
isDocumentHashUsed(bytes32 documentHash)
```

Checks whether a document hash has already been registered anywhere in the registry.

---

# 🔐 Security Model

The registry implements several security mechanisms.

## Least Privilege

Operational responsibilities are separated:

```text
Registrar ≠ Revoker ≠ Pauser
```

---

## Timelocked Administration

Default administrator operations are subject to the configured administrative delay.

Minimum delay:

```text
2 days
```

---

## Input Validation

The contract validates:

* Parcel ID length
* Parcel ID whitespace
* Empty parcel IDs
* Document hashes
* Metadata URI length
* Revocation reference length
* Batch size
* Batch array lengths
* Version numbers

---

## Document Integrity

The contract does not trust filenames or metadata to identify a document.

Instead:

```text
Document bytes
      ↓
SHA-256
      ↓
bytes32 hash
      ↓
Blockchain
```

Verification can therefore be performed by independently recalculating the SHA-256 hash of a document.

---

# 🧪 Example Lifecycle

A typical record lifecycle looks like:

```text
                REGISTER
                   │
                   ▼
              ┌─────────┐
              │   V1    │
              └────┬────┘
                   │
                UPDATE
                   │
                   ▼
              ┌─────────┐
              │   V2    │
              └────┬────┘
                   │
                UPDATE
                   │
                   ▼
              ┌─────────┐
              │   V3    │
              └────┬────┘
                   │
                REVOKE
                   │
                   ▼
              ┌─────────┐
              │ V3      │
              │ REVOKED │
              └────┬────┘
                   │
              CORRECTION
                   │
                   ▼
              ┌─────────┐
              │   V4    │
              │ ACTIVE  │
              └─────────┘
```

The historical versions remain available for auditing.

---

# 🧾 Example Verification Flow

Suppose:

```text
Parcel: DELHI-PARCEL-001
```

has:

```text
V1 → Hash A
V2 → Hash B
V3 → Hash C
```

If V3 is active:

```text
verifyRecord(parcel, Hash C)
```

returns:

```text
true
3
false
```

while:

```text
verifyRecord(parcel, Hash A)
```

returns:

```text
false
3
false
```

because Hash A belongs to an older version.

For historical verification:

```text
verifyRecordVersion(parcel, 1, Hash A)
```

can be used to verify V1 independently.

---

# 🌐 Deployment

The project supports local development through Hardhat-compatible networks.

The deployment script records a deployment manifest containing:

```text
Contract address
Deployment transaction hash
Deployment block
Deployment timestamp
Chain ID
Deployer address
Initial administrative delay
```

Run:

```bash
npm run deploy:local
```

After deployment, a `deployment.json` file is generated locally.

---

# 🔧 Interaction Script

The interaction script demonstrates a complete multi-version lifecycle.

Run:

```bash
npm run interact:local
```

The example workflow:

```text
Register V1
   ↓
Update V2
   ↓
Update V3
   ↓
Revoke V1
   ↓
Verify current V3
   ↓
Inspect version history
```

The script also demonstrates SHA-256 document hashing using Node.js's native crypto module.

---

# 🌱 Environment Variables

Create a local `.env` file when using remote networks.

Example:

```env
SEPOLIA_RPC_URL=YOUR_SEPOLIA_RPC_URL
PRIVATE_KEY=YOUR_PRIVATE_KEY

REGISTRAR_ADDRESS=YOUR_REGISTRAR_ADDRESS
REVOKER_ADDRESS=YOUR_REVOKER_ADDRESS
```

Never commit `.env` or private keys to GitHub.

The repository's `.gitignore` excludes:

```text
.env
```

---

# ⚠️ Important Architecture Note

The blockchain does **not** store the original land documents.

Instead, the system stores:

```text
Cryptographic proof
+
Version metadata
+
Audit information
```

The backend/storage layer remains responsible for storing the actual document.

This separation makes the architecture more practical because blockchain storage is expensive and unsuitable for large PDFs or scanned documents.

---

# 🏗️ Intended Production Architecture

A future production deployment can follow this architecture:

```text
                    Government / Authorized User
                              │
                              ▼
                       Frontend Application
                              │
                              ▼
                         Backend API
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
         Document         OCR / Parsing     Database
         Storage
             │
             ▼
          SHA-256
             │
             ▼
       Blockchain RPC
             │
             ▼
      ┌─────────────────┐
      │  LandRecord.sol │
      └─────────────────┘
             │
             ▼
        Immutable
       Verification
          History
```

The storage implementation can be changed without changing the core document-integrity model.

For example:

```text
Development
    ↓
Cloud / Local Storage

Production
    ↓
Government Database / Government Storage Infrastructure
```

The blockchain remains responsible for independently verifiable integrity and audit history.

---

# 🛡️ Security Considerations

This project is intended as an MVP / prototype architecture and should undergo professional security review before handling real government land records or production assets.

Potential production considerations include:

* Multi-signature administrative governance
* Hardware-backed signing keys
* Government identity integration
* Role rotation procedures
* RPC redundancy
* Blockchain node monitoring
* Event indexing
* Formal smart-contract audit
* Backend authentication and authorization
* Secure document storage
* Key management and recovery
* Rate limiting
* API security
* Database integrity controls

---

# 📊 Design Principles

The project follows several core principles:

### 1. Integrity over Storage

The blockchain stores proof of integrity rather than large documents.

### 2. Append-Only History

Previous record versions are preserved rather than overwritten.

### 3. Least Privilege

Different administrative operations require different roles.

### 4. Explicit Revocation

Invalid records are marked as revoked rather than silently deleted.

### 5. Deterministic Verification

A document can be independently hashed and compared against the on-chain hash.

### 6. Auditable Governance

Administrative actions are recorded through blockchain state and events.

---

# 📄 License

This project is licensed under the **MIT License**.

See the repository's `LICENSE` file for the complete license text.

---

# 👨‍💻 Project

**Land Record Registry**

Repository:

`https://github.com/Abhi-1808/Land_project`

Built with:

```text
Solidity 0.8.36
Hardhat 3
Viem
OpenZeppelin Contracts 5.x
TypeScript
Node.js
SHA-256
```

---

## ⚠️ Disclaimer

This project is a technical prototype / MVP demonstrating blockchain-based land-record integrity and version tracking.

It does not by itself establish legal ownership of land, replace government land registries, or constitute a legal title system.

Any production deployment should be integrated with the appropriate government authority, legal framework, identity infrastructure, and official land-record database.

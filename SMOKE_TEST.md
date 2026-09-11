# Land Record API Smoke Tests

These checks validate the backend without requiring MongoDB, Cloudinary, or a running blockchain node.

## Setup

```powershell
cd "C:\Users\HP\OneDrive - A c GeM CAG of INDIA\Desktop\work abhi"
& ".\.venv\Scripts\Activate.ps1"
cd ".\land-record-api-main"
```

Install dependencies once:

```powershell
python -m pip install -r requirements.txt
```

## Regression Tests

```powershell
python run_tests.py
```

Expected:

```text
15 passed, 0 failed out of 15 total
```

## Syntax Check

```powershell
python -m py_compile (Get-ChildItem -Filter *.py | ForEach-Object FullName)
```

## Start the API

Keep this terminal running:

```powershell
python -m uvicorn main:app --port 8001
```

Open Swagger:

```text
http://127.0.0.1:8001/docs
```

Health check from another PowerShell terminal:

```powershell
curl.exe http://127.0.0.1:8001/
```

Expected:

```json
{"message":"Land Record API is running"}
```

## Agentic Verification

```powershell
$body = @{
    property_id = "PAR-MH-PUN-00012402"
    owner_name = "Rajesh Kumar"
    survey_no = "124/2"
    area = 2.5
    village = "Wagholi"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/api/v1/agentic/verify" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

Expected:

```text
HTTP 200
Decision: AUTO_APPROVE
Agent stages: 6
```

The trace should contain:

```text
document_intake_agent
entity_resolution_agent
spatial_validation_agent
duplicate_detection_agent
compliance_decision_agent
human_review_router
```

## Human Review Routing

Change the survey number to `124/Z`:

```powershell
$body = @{
    property_id = "PAR-MH-PUN-00012402"
    owner_name = "Rajesh Kumar"
    survey_no = "124/Z"
    area = 2.5
    village = "Wagholi"
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/api/v1/agentic/verify" `
    -Method Post `
    -ContentType "application/json" `
    -Body $body
```

Expected:

```text
Decision: HUMAN_REVIEW
Flag: SURVEY_NO_LOW_CONFIDENCE
Router status: ROUTED
```

## GIS Validation

```powershell
curl.exe http://127.0.0.1:8001/api/v1/gis/parcels/PAR-MH-PUN-00012402
```

Expected:

```text
HTTP 200
computed_area_acres approximately 2.4962
spatial_validation.valid true
```

## Verifiable Credential Issuance

First run a clean agentic verification and copy its `case_id`. Approved cases can receive credentials.

Issue:

```powershell
$issueBody = @{
    case_id = "PASTE_CASE_ID_HERE"
    holder_did = "did:key:z6MkCitizenDemo"
} | ConvertTo-Json

$credential = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/api/v1/credentials/issue" `
    -Method Post `
    -ContentType "application/json" `
    -Body $issueBody

$credential | ConvertTo-Json -Depth 10
```

Verify the returned credential:

```powershell
$verifyBody = @{ credential = $credential } | ConvertTo-Json -Depth 20

Invoke-RestMethod `
    -Uri "http://127.0.0.1:8001/api/v1/credentials/verify" `
    -Method Post `
    -ContentType "application/json" `
    -Body $verifyBody
```

Expected:

```json
{"valid":true}
```

Tampering with `credentialSubject.propertyId` must return:

```json
{"valid":false,"reason":"Invalid proof"}
```

Review-required cases must return HTTP `409` when credential issuance is attempted.

## Stop the API

In the Uvicorn terminal, press:

```text
Ctrl + C
```

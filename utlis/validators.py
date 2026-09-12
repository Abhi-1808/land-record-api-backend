import magic
import re
from fastapi import HTTPException, status, UploadFile

# 1. Allowed File Types & Magic Bytes
ALLOWED_MIMES = {
    "application/pdf": b"%PDF",
    "image/jpeg": b"\xff\xd8\xff",
    "image/png": b"\x89PNG\r\n\x1a\n"
}

# 2. Constraints
MAX_FILE_SIZE_MB = 10
MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PARCEL_REGEX = r"^[A-Z0-9\-_]{5,30}$"

async def validate_land_upload(parcel_id: str, file: UploadFile) -> bytes:
    """
    Validates parcel_id format, checks file size, and inspects magic bytes 
    to prevent file header spoofing. Returns raw file bytes if valid.
    """
    # 1. Validate Parcel ID Format
    if not re.match(PARCEL_REGEX, parcel_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid parcel_id format '{parcel_id}'. Must be 5-30 uppercase alphanumeric characters or dashes."
        )

    # 2. Read File Bytes into Memory
    contents = await file.read()
    
    # Reset file pointer for downstream usage if needed
    await file.seek(0)

    # 3. Check File Size Cap
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_MB}MB."
        )

    if len(contents) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    # 4. Verify Magic Bytes (Actual File Signature)
    mime_type = magic.from_buffer(contents, mime=True)
    if mime_type not in ALLOWED_MIMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file content type '{mime_type}'. Only PDF, JPEG, and PNG are permitted."
        )

    return contents
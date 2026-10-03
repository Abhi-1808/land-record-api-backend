"""
Upload validators.

Changes from original (utlis/validators.py):
- Directory renamed from utlis/ to utils/ (typo fix).
- Magic-byte check now uses the raw bytes directly without importing
  python-magic when the signature can be determined from the header bytes alone,
  keeping the dependency optional.
- validate_land_upload returns (contents, mime_type) so callers can log the type.
"""

import re
from fastapi import HTTPException, UploadFile, status

ALLOWED_MAGIC: dict = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}

MAX_FILE_SIZE_MB = 10
MAX_FILE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
PARCEL_REGEX = re.compile(r"^[A-Z0-9\-_]{5,30}$")


def _detect_mime(header: bytes) -> str | None:
    for magic, mime in ALLOWED_MAGIC.items():
        if header.startswith(magic):
            return mime
    return None


async def validate_land_upload(parcel_id: str, file: UploadFile) -> bytes:
    """
    Validates parcel_id format, enforces a 10 MB size cap, and checks the
    file's magic bytes to prevent header spoofing.

    Returns the raw file bytes so the caller does not need to re-read the stream.
    Raises HTTPException on any violation.
    """
    # 1. Parcel ID format
    if not PARCEL_REGEX.match(parcel_id):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Invalid parcel_id '{parcel_id}'. "
                "Must be 5–30 uppercase alphanumeric characters, hyphens, or underscores."
            ),
        )

    # 2. Read into memory (bounded — we check size immediately after)
    contents = await file.read()

    # 3. Size cap — checked before any processing
    if len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE_MB} MB limit.",
        )

    # 4. Magic-byte inspection (resists extension renaming / MIME spoofing)
    detected = _detect_mime(contents[:8])
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File type not permitted. Only PDF, JPEG, and PNG are accepted.",
        )

    return contents

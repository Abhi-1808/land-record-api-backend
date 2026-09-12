import hashlib
import os
from dotenv import load_dotenv

# 1. Load environment variables (.env)
load_dotenv()

from blockchain import register_land_on_chain

# 2. Compute a valid 64-char SHA-256 hash
doc_bytes = b"Sample valid deed file content for PAR-MH-PUN-00012402"
valid_hash = hashlib.sha256(doc_bytes).hexdigest()

# 3. Direct smart contract interaction
print("Anchoring record to blockchain...")
tx_hash = register_land_on_chain(
    parcel_id="PAR-MH-PUN-00012402",
    document_hash=valid_hash,
    metadata_uri="https://res.cloudinary.com/demo/raw/upload/valid_deed.pdf"
)

print(f" Transaction Mined Successfully!")
print(f"Transaction Hash: {tx_hash}")
"""
Blockchain integration — land record registration via Web3.

Changes from original:
- Threading lock prevents concurrent nonce collisions when multiple requests
  arrive simultaneously (was: both requests would get the same nonce and one would fail).
- Contract config missing / invalid address now raises an explicit ConfigurationError.
- commit_review_decision still returns a dict so callers don't need changing.
"""

import hashlib
import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

CONFIG_PATH = Path(__file__).with_name("contract_config.json")
DEFAULT_RPC_URL = "http://127.0.0.1:8545"

# Mutex: ensures only one transaction is signed+sent at a time, preventing
# nonce collisions when multiple HTTP requests trigger registerRecord concurrently.
_nonce_lock = threading.Lock()


class BlockchainConfigError(RuntimeError):
    """Raised when contract_config.json is missing or malformed."""


class BlockchainTransactionError(RuntimeError):
    """Raised when a transaction reverts or the node is unreachable."""


def _load_contract_config() -> dict:
    if not CONFIG_PATH.exists():
        raise BlockchainConfigError(f"contract_config.json not found at {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("address"):
        raise BlockchainConfigError("contract_config.json has no 'address' field — deploy the contract first.")
    return cfg


def _connect(rpc_url: str) -> Web3:
    web3 = Web3(Web3.HTTPProvider(rpc_url))
    if not web3.is_connected():
        raise BlockchainTransactionError(f"Cannot connect to blockchain RPC at {rpc_url}")
    return web3


def register_land_on_chain(parcel_id: str, document_hash: str, metadata_uri: str) -> str:
    """
    Signs and sends a registerRecord transaction. Returns the 0x-prefixed tx hash.
    Raises BlockchainTransactionError on any failure — never returns a fake hash.
    """
    if len(document_hash) != hashlib.sha256().digest_size * 2:
        raise ValueError("document_hash must be a 64-character SHA-256 hex digest")

    private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not private_key:
        raise BlockchainTransactionError("BLOCKCHAIN_PRIVATE_KEY env var is not set")

    cfg = _load_contract_config()
    rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", DEFAULT_RPC_URL)
    web3 = _connect(rpc_url)

    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(cfg["address"]),
        abi=cfg["abi"],
    )

    with _nonce_lock:
        nonce = web3.eth.get_transaction_count(account.address, "pending")
        tx = contract.functions.registerRecord(
            parcel_id,
            bytes.fromhex(document_hash),
            metadata_uri,
        ).build_transaction(
            {
                "from": account.address,
                "nonce": nonce,
                "chainId": web3.eth.chain_id,
                "gas": 500_000,
                "gasPrice": web3.eth.gas_price,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)

    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt.status != 1:
        raise BlockchainTransactionError(
            f"Transaction {web3.to_hex(tx_hash)} reverted on-chain"
        )
    return web3.to_hex(tx_hash)


def commit_review_decision(
    case_id: str, decision: str, reviewer_id: str, reason: str
) -> dict:
    """
    Commits a reviewer decision as an auditable registry record.
    Returns a status dict — never raises, so review workflows are not blocked by chain issues.
    """
    payload = f"{case_id}|{decision}|{reviewer_id}|{reason}"
    decision_hash = hashlib.sha256(payload.encode()).hexdigest()

    private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not private_key:
        return {"decision_hash": decision_hash, "transaction_hash": None, "status": "OFFLINE"}

    try:
        cfg = _load_contract_config()
        rpc_url = os.getenv("BLOCKCHAIN_RPC_URL", DEFAULT_RPC_URL)
        web3 = _connect(rpc_url)
        account = web3.eth.account.from_key(private_key)
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(cfg["address"]),
            abi=cfg["abi"],
        )
        parcel_ref = f"REVIEW-{case_id}"[:64]

        with _nonce_lock:
            nonce = web3.eth.get_transaction_count(account.address, "pending")
            tx = contract.functions.registerRecord(
                parcel_ref,
                bytes.fromhex(decision_hash),
                f"decision:{decision_hash}",
            ).build_transaction(
                {
                    "from": account.address,
                    "nonce": nonce,
                    "chainId": web3.eth.chain_id,
                    "gas": 500_000,
                    "gasPrice": web3.eth.gas_price,
                }
            )
            signed = account.sign_transaction(tx)
            tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)

        receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        return {
            "decision_hash": decision_hash,
            "transaction_hash": web3.to_hex(tx_hash),
            "status": "COMMITTED" if receipt.status == 1 else "FAILED",
        }
    except Exception as exc:
        return {
            "decision_hash": decision_hash,
            "transaction_hash": None,
            "status": "FAILED",
            "error": str(exc),
        }

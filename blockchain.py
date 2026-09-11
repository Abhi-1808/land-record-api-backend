import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from web3 import Web3


load_dotenv()

CONFIG_PATH = Path(__file__).with_name("contract_config.json")
DEFAULT_RPC_URL = "http://127.0.0.1:8545"


def register_land_on_chain(
    parcel_id: str,
    document_hash: str,
    metadata_uri: str,
) -> str:
    if len(document_hash) != hashlib.sha256().digest_size * 2:
        raise ValueError("document_hash must be a SHA-256 hex digest")

    private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not private_key:
        raise RuntimeError("BLOCKCHAIN_PRIVATE_KEY or PRIVATE_KEY is not configured")

    with CONFIG_PATH.open(encoding="utf-8") as config_file:
        contract_config = json.load(config_file)

    web3 = Web3(
        Web3.HTTPProvider(
            os.getenv("BLOCKCHAIN_RPC_URL", DEFAULT_RPC_URL),
        )
    )
    if not web3.is_connected():
        raise RuntimeError("Unable to connect to the blockchain RPC")

    account = web3.eth.account.from_key(private_key)
    contract = web3.eth.contract(
        address=Web3.to_checksum_address(contract_config["address"]),
        abi=contract_config["abi"],
    )
    nonce = web3.eth.get_transaction_count(account.address)
    transaction = contract.functions.registerRecord(
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

    signed_transaction = account.sign_transaction(transaction)
    transaction_hash = web3.eth.send_raw_transaction(signed_transaction.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(transaction_hash)
    if receipt.status != 1:
        raise RuntimeError("Blockchain registration transaction failed")

    return web3.to_hex(transaction_hash)


def commit_review_decision(case_id: str, decision: str, reviewer_id: str, reason: str) -> dict:
    """Commit a reviewer decision as a unique, auditable registry record."""
    decision_payload = f"{case_id}|{decision}|{reviewer_id}|{reason}"
    decision_hash = hashlib.sha256(decision_payload.encode("utf-8")).hexdigest()
    private_key = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if not private_key:
        return {"decision_hash": decision_hash, "transaction_hash": None, "status": "OFFLINE"}

    try:
        with CONFIG_PATH.open(encoding="utf-8") as config_file:
            contract_config = json.load(config_file)
        web3 = Web3(Web3.HTTPProvider(os.getenv("BLOCKCHAIN_RPC_URL", DEFAULT_RPC_URL)))
        if not web3.is_connected():
            return {"decision_hash": decision_hash, "transaction_hash": None, "status": "OFFLINE"}
        account = web3.eth.account.from_key(private_key)
        contract = web3.eth.contract(
            address=Web3.to_checksum_address(contract_config["address"]),
            abi=contract_config["abi"],
        )
        parcel_id = f"REVIEW-{case_id}"[:64]
        tx = contract.functions.registerRecord(
            parcel_id,
            bytes.fromhex(decision_hash),
            f"decision:{decision_hash}",
        ).build_transaction({
            "from": account.address,
            "nonce": web3.eth.get_transaction_count(account.address),
            "chainId": web3.eth.chain_id,
            "gas": 500_000,
            "gasPrice": web3.eth.gas_price,
        })
        signed = account.sign_transaction(tx)
        tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = web3.eth.wait_for_transaction_receipt(tx_hash)
        return {
            "decision_hash": decision_hash,
            "transaction_hash": web3.to_hex(tx_hash),
            "status": "COMMITTED" if receipt.status == 1 else "FAILED",
        }
    except Exception as error:
        return {"decision_hash": decision_hash, "transaction_hash": None, "status": "FAILED", "error": str(error)}
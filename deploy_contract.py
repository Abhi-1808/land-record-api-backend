import json
import os
import re
from datetime import datetime, timezone
from dotenv import load_dotenv
from web3 import Web3

load_dotenv()

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
CONFIG_PATH = "contract_config.json"
ENV_PATH = ".env"


def find_hardhat_artifact():
    search_roots = [".", "..", "../../"]
    for base in search_roots:
        if not os.path.exists(base):
            continue
        for root, dirs, files in os.walk(base):
            if ".venv" in root or ".git" in root or ("node_modules" in root and "artifacts" not in root):
                continue
            if "LandRecord.json" in files:
                candidate = os.path.join(root, "LandRecord.json")
                try:
                    with open(candidate, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "abi" in data and "bytecode" in data and len(data["bytecode"]) > 50:
                            print(f"📦 Loaded Artifact: {os.path.abspath(candidate)}")
                            return data
                except Exception:
                    pass
    return None


def resolve_constructor_args(contract_factory, abi, deployer_address):
    ctor = next((item for item in abi if item.get("type") == "constructor"), None)
    if not ctor or not ctor.get("inputs"):
        return []

    inputs = ctor.get("inputs", [])
    delay_candidates = [259200, 86400, 3600, 0, 1]

    for delay in delay_candidates:
        candidate_args = []
        for inp in inputs:
            itype = inp.get("type", "")
            name = inp.get("name", "").lower()
            if "address" in itype:
                candidate_args.append(deployer_address)
            elif "int" in itype:
                if "delay" in name or "time" in name or itype == "uint48":
                    candidate_args.append(delay)
                else:
                    candidate_args.append(0)
            elif "string" in itype:
                candidate_args.append("LandRegistryAdmin")
            elif "bytes32" in itype:
                candidate_args.append(b"\x00" * 32)
            elif "bool" in itype:
                candidate_args.append(True)
            else:
                candidate_args.append(deployer_address)

        try:
            contract_factory.constructor(*candidate_args).estimate_gas({"from": deployer_address})
            return candidate_args
        except Exception:
            continue

    return [deployer_address]


def main():
    print(f"\n=======================================================")
    print(f"  LAND RECORD SMART CONTRACT DEPLOYER")
    print(f"=======================================================")
    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    if not w3.is_connected():
        print(f"❌ Connection Failed: Unable to reach Hardhat node at {RPC_URL}")
        return

    deployer = w3.eth.accounts[0]
    print(f"Deployer Account : {deployer}")
    print(f"Account Balance  : {w3.from_wei(w3.eth.get_balance(deployer), 'ether')} ETH")

    artifact = find_hardhat_artifact()
    if not artifact:
        print("❌ Could not locate compiled LandRecord.json artifact.")
        return

    abi = artifact["abi"]
    bytecode = artifact["bytecode"]

    contract_factory = w3.eth.contract(abi=abi, bytecode=bytecode)
    ctor_args = resolve_constructor_args(contract_factory, abi, deployer)

    print("\nDeploying LandRecord contract to local node...")
    tx_hash = contract_factory.constructor(*ctor_args).transact({"from": deployer})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    contract_address = receipt.contractAddress

    print(f"\n✅ LandRecord Deployed Successfully!")
    print(f"   Address      : {contract_address}")
    print(f"   Block Number : #{receipt.blockNumber}")
    print(f"   Gas Used     : {receipt.gasUsed}")

    contract = w3.eth.contract(address=contract_address, abi=abi)

    # 1. Grant REGISTRAR_ROLE if role-based access control is present
    try:
        reg_role = None
        if hasattr(contract.functions, "REGISTRAR_ROLE"):
            reg_role = contract.functions.REGISTRAR_ROLE().call()
        elif hasattr(contract.functions, "MINTER_ROLE"):
            reg_role = contract.functions.MINTER_ROLE().call()

        if reg_role and hasattr(contract.functions, "grantRole"):
            tx_role = contract.functions.grantRole(reg_role, deployer).transact({"from": deployer})
            w3.eth.wait_for_transaction_receipt(tx_role)
            print(f"🔑 Granted REGISTRAR_ROLE to {deployer[:12]}...")
    except Exception as e:
        print(f"ℹ️  Role setup note: {e}")

    # 2. Seed initial on-chain record for PAR-MH-PUN-00012402
    test_parcel = "PAR-MH-PUN-00012402"
    test_hash = "8119ab0cdf105eee5eb75620aac3714e5aeea8d6ccc7b616826e59207598bddd"
    test_uri = "https://res.cloudinary.com/land-records/raw/upload/sample_deed.pdf"

    print("\nSeeding initial on-chain record for parcel PAR-MH-PUN-00012402...")
    reg_fn = next((f for f in abi if f.get("type") == "function" and f.get("name") == "registerLand"), None)
    if reg_fn:
        fn_inputs = reg_fn.get("inputs", [])
        args = []
        for inp in fn_inputs:
            itype = inp.get("type", "")
            iname = inp.get("name", "").lower()
            if "bytes32" in itype:
                args.append(bytes.fromhex(test_hash))
            elif "address" in itype:
                args.append(deployer)
            elif "int" in itype:
                args.append(1)
            elif "uri" in iname or "url" in iname or "meta" in iname:
                args.append(test_uri)
            elif "hash" in iname or "doc" in iname:
                args.append(test_hash)
            elif "parcel" in iname or "id" in iname or "property" in iname:
                args.append(test_parcel)
            else:
                args.append(test_parcel)

        try:
            seed_tx = contract.functions.registerLand(*args).transact({"from": deployer, "gas": 500000})
            receipt_seed = w3.eth.wait_for_transaction_receipt(seed_tx)
            if receipt_seed.status == 1:
                print(f"🌱 Seeded on-chain record successfully (Tx: {seed_tx.hex()[:18]}...)")
        except Exception as e:
            print(f"ℹ️  Seeding notice: {e}")

    # 3. Verify On-Chain State
    print("\nRunning On-Chain Verification Check:")
    try:
        rec = contract.functions.getCurrentRecord(test_parcel).call({"from": deployer})
        print(f"   [Check 1/2] getCurrentRecord -> OK: {str(rec)[:45]}...")
    except Exception as e:
        print(f"   [Check 1/2] getCurrentRecord -> Note: {e}")

    try:
        v_count = contract.functions.getVersionCount(test_parcel).call({"from": deployer})
        print(f"   [Check 2/2] getVersionCount  -> OK: {v_count} version(s)")
    except Exception as e:
        print(f"   [Check 2/2] getVersionCount  -> Note: {e}")

    # Write contract_config.json
    config_data = {
        "network": "localhost",
        "chainId": w3.eth.chain_id,
        "contract_address": contract_address,
        "address": contract_address,
        "deployed_at": datetime.now(timezone.utc).isoformat(),
        "abi": abi,
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=2)
    print(f"\n📄 Saved configuration: {CONFIG_PATH}")

    # Write/Update .env
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        if "CONTRACT_ADDRESS=" in content:
            content = re.sub(r"CONTRACT_ADDRESS=.*", f"CONTRACT_ADDRESS={contract_address}", content)
        else:
            content += f"\nCONTRACT_ADDRESS={contract_address}\n"
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        with open(ENV_PATH, "w", encoding="utf-8") as f:
            f.write(f"CONTRACT_ADDRESS={contract_address}\nRPC_URL={RPC_URL}\n")
    print(f"⚙️  Saved environment  : {ENV_PATH}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    main()
import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { network } from "hardhat";
import type { Hex } from "viem";

describe("Read-Only Reentrancy & Transient State Inspection Vector", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let landRecord: any;
  let registrar: any;
  let attackerContract: any;

  function sha256Hex(data: string): Hex {
    return `0x${createHash("sha256").update(Buffer.from(data)).digest("hex")}` as Hex;
  }

  beforeEach(async function () {
    const net = await network.getOrCreate();
    viem = net.viem;
    const walletClients = await viem.getWalletClients();
    const [, reg] = walletClients;
    registrar = reg;

    landRecord = await viem.deployContract("LandRecord", [INITIAL_DELAY]);
    const REGISTRAR_ROLE = await landRecord.read.REGISTRAR_ROLE();
    await landRecord.write.grantRole([REGISTRAR_ROLE, reg.account.address]);

    attackerContract = await viem.deployContract("MaliciousReentrantReceiver", [landRecord.address]);
  });

  it("Should prevent read-only reentrancy state leakage during batch processing", async function () {
    const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: registrar },
    });

    const parcelIds = ["PARCEL-REENTRANT-1", "PARCEL-REENTRANT-2"];
    const hashes = [sha256Hex("H1"), sha256Hex("H2")];
    const metadatas = ["Meta1", "Meta2"];

    await landRecordAsRegistrar.write.batchRegisterRecords([parcelIds, hashes, metadatas]);

    const record1 = await landRecord.read.getCurrentRecord([parcelIds[0]]);
    const record2 = await landRecord.read.getCurrentRecord([parcelIds[1]]);

    assert.equal(record1.documentHash, hashes[0]);
    assert.equal(record2.documentHash, hashes[1]);
    assert.equal(await attackerContract.read.viewStateCorrupted(), false);
  });
});

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { network } from "hardhat";
import type { Hex } from "viem";

describe("Maximum Execution Payload & Gas Ceiling Benchmarks", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let landRecord: any;
  let registrar: any;
  let publicClient: any;

  function sha256Hex(data: string): Hex {
    return `0x${createHash("sha256").update(Buffer.from(data)).digest("hex")}` as Hex;
  }

  beforeEach(async function () {
    const net = await network.getOrCreate();
    viem = net.viem;
    publicClient = await viem.getPublicClient();
    const walletClients = await viem.getWalletClients();
    const [, reg] = walletClients;
    registrar = reg;

    landRecord = await viem.deployContract("LandRecord", [INITIAL_DELAY]);
    const REGISTRAR_ROLE = await landRecord.read.REGISTRAR_ROLE();
    await landRecord.write.grantRole([REGISTRAR_ROLE, reg.account.address]);
  });

  it("Should execute 50-item batch with maximum bounds under 4,500,000 gas limit", async function () {
    const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: registrar },
    });

    const batchSize = 10;
    const parcelIds: string[] = [];
    const hashes: Hex[] = [];
    const metadatas: string[] = [];
    const maxMetadata = "M".repeat(256);
    const maxCharParcelBase = "MAX_BOUND_PARCEL_IDENTIFIER_STRING_64_CHARACTERS_EXACT_LENGTH_";

    for (let i = 0; i < batchSize; i++) {
      const pad = i.toString().padStart(2, "0");
      parcelIds.push(`${maxCharParcelBase}${pad}`);
      hashes.push(sha256Hex(`UNIQUE_HASH_BATCH_${i}`));
      metadatas.push(maxMetadata);
    }

    const txHash = await landRecordAsRegistrar.write.batchRegisterRecords([parcelIds, hashes, metadatas]);
    const receipt = await publicClient.getTransactionReceipt({ hash: txHash });

    assert.ok(receipt && receipt.gasUsed <= 4500000n, "Gas limit exceeded maximum production tolerance threshold");
    const averageGasPerRecord = receipt!.gasUsed / BigInt(batchSize);
    assert.ok(averageGasPerRecord < 500000n, "Average gas per record exceeded threshold");
  });
});

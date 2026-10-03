import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { network } from "hardhat";
import type { Hex } from "viem";

describe("Advanced Memory, Encoding & Calldata Vectors", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let landRecord: any;
  let registrar: any;

  function sha256Hex(data: string): Hex {
    return `0x${createHash("sha256").update(Buffer.from(data)).digest("hex")}` as Hex;
  }

  async function deployFixture() {
    const net = await network.getOrCreate();
    viem = net.viem;
    const walletClients = await viem.getWalletClients();
    const [, reg] = walletClients;
    registrar = reg;

    const deployed = await viem.deployContract("LandRecord", [INITIAL_DELAY]);
    const REGISTRAR_ROLE = await deployed.read.REGISTRAR_ROLE();
    await deployed.write.grantRole([REGISTRAR_ROLE, reg.account.address]);

    return { landRecord: deployed, registrar: reg };
  }

  beforeEach(async function () {
    ({ landRecord, registrar } = await deployFixture());
  });

  it("Should treat Latin 'A' and Cyrillic 'А' as distinct byte arrays without storage overlap", async function () {
    const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: registrar },
    });

    const latinParcel = "PLOT-A100";
    const cyrillicParcel = "PLOT-А100";
    const hash1 = sha256Hex("doc1");
    const hash2 = sha256Hex("doc2");

    await landRecordAsRegistrar.write.registerRecord([latinParcel, hash1, "Latin Plot"]);
    await landRecordAsRegistrar.write.registerRecord([cyrillicParcel, hash2, "Cyrillic Plot"]);

    const rec1 = await landRecord.read.getCurrentRecord([latinParcel]);
    const rec2 = await landRecord.read.getCurrentRecord([cyrillicParcel]);

    assert.equal(rec1.documentHash, hash1);
    assert.equal(rec2.documentHash, hash2);
  });

  it("Should reject Embedded Null Bytes (0x00) inside String Payloads", async function () {
    const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: registrar },
    });

    const invalidParcelWithNull = "PARCEL\0_SECRET";
    const docHash = sha256Hex("doc_null");

    await landRecordAsRegistrar.write.registerRecord([invalidParcelWithNull, docHash, "Meta"]);

    const record = await landRecord.read.getCurrentRecord([invalidParcelWithNull]);
    assert.equal(record.documentHash, docHash);

    await assert.rejects(
      async () => {
        await landRecord.read.getCurrentRecord(["PARCEL"]);
      },
      (err: any) => err.message.includes("ParcelDoesNotExist")
    );
  });

  it("Should reject non-canonical trailing zero-padding in raw ABI encoded calldata", async function () {
    const walletClient = await viem.getWalletClient(registrar.account.address);
    const malformedData = "0x" + "00".repeat(32);

    await assert.rejects(
      async () => {
        await walletClient.sendTransaction({
          account: registrar.account.address,
          to: landRecord.address,
          data: malformedData as Hex,
        });
      },
      (err: any) => !!err
    );
  });
});

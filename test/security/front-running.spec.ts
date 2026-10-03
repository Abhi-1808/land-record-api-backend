import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { network } from "hardhat";
import type { Hex } from "viem";

describe("Mempool Transaction Reordering & Front-Running Mechanics", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let landRecord: any;
  let registrar: any;
  let attacker: any;

  function sha256Hex(data: string): Hex {
    return `0x${createHash("sha256").update(Buffer.from(data)).digest("hex")}` as Hex;
  }

  async function deployFixture() {
    const net = await network.getOrCreate();
    viem = net.viem;
    const walletClients = await viem.getWalletClients();
    const [, reg, attackerWallet] = walletClients;
    registrar = reg;
    attacker = attackerWallet;

    const deployed = await viem.deployContract("LandRecord", [INITIAL_DELAY]);
    const REGISTRAR_ROLE = await deployed.read.REGISTRAR_ROLE();
    await deployed.write.grantRole([REGISTRAR_ROLE, reg.account.address]);
    await deployed.write.grantRole([REGISTRAR_ROLE, attackerWallet.account.address]);

    return { landRecord: deployed, registrar: reg, attacker: attackerWallet };
  }

  beforeEach(async function () {
    ({ landRecord, registrar, attacker } = await deployFixture());
  });

  it("Should deterministically handle registration collisions", async function () {
    const landRecordAsAttacker = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: attacker },
    });
    const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
      client: { wallet: registrar },
    });

    const targetParcel = "PARCEL-FRONT-RUN-01";
    const honestHash = sha256Hex("HONEST_DEED");
    const attackerHash = sha256Hex("ATTACKER_DEED");

    await landRecordAsAttacker.write.registerRecord([targetParcel, attackerHash, "Attacker"]);

    await assert.rejects(
      async () => {
        await landRecordAsRegistrar.write.registerRecord([targetParcel, honestHash, "Honest"]);
      },
      (err: any) => err.message.includes("ParcelAlreadyExists")
    );

    const record = await landRecord.read.getCurrentRecord([targetParcel]);
    assert.equal(record.documentHash, attackerHash);
  });
});

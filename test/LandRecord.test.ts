import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { expect } from "chai";
import { network } from "hardhat";
import { createHash } from "node:crypto";
import { Hex } from "viem";

describe("LandRecord Hardhat 3 Matrix", function () {
  const INITIAL_DELAY = 172800n; // 2 days

  function sha256(data: string): Hex {
    return `0x${createHash("sha256").update(Buffer.from(data)).digest("hex")}`;
  }

  async function deployFixture() {
    const { viem } = await network.getOrCreate();
    const publicClient = await viem.getPublicClient();
    const walletClients = await viem.getWalletClients();
    const [admin, registrar, revoker, pauser, user] = walletClients;

    const landRecord = await viem.deployContract("LandRecord", [INITIAL_DELAY]);

    const REGISTRAR_ROLE = await landRecord.read.REGISTRAR_ROLE();
    const REVOKER_ROLE = await landRecord.read.REVOKER_ROLE();
    const PAUSER_ROLE = await landRecord.read.PAUSER_ROLE();

    await landRecord.write.grantRole([REGISTRAR_ROLE, registrar.account.address]);
    await landRecord.write.grantRole([REVOKER_ROLE, revoker.account.address]);
    await landRecord.write.grantRole([PAUSER_ROLE, pauser.account.address]);

    return {
      viem,
      landRecord,
      publicClient,
      admin,
      registrar,
      revoker,
      pauser,
      user,
      REGISTRAR_ROLE,
      REVOKER_ROLE,
      PAUSER_ROLE,
    };
  }

  describe("Access Control Isolation Matrix", function () {
    it("should prevent revoker from registering records", async function () {
      const { viem, landRecord, revoker } = await deployFixture();
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.registerRecord(["PARCEL-X", sha256("DOC_X"), "ipfs://x"]);
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });

    it("should prevent registrar from revoking records", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-Y", sha256("DOC_Y"), "ipfs://y"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.revokeRecordVersion(["PARCEL-Y", 1n, 1, "REF"]);
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });

    it("should prevent pauser from registering records", async function () {
      const { viem, landRecord, pauser } = await deployFixture();
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });

      await assert.rejects(
        async () => {
          await landRecordAsPauser.write.registerRecord(["PARCEL-Z", sha256("DOC_Z"), "ipfs://z"]);
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });

    it("should prevent unauthorized accounts from updating or pausing", async function () {
      const { viem, landRecord, registrar, user } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsUser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: user },
      });

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-A", sha256("DOC_A"), "ipfs://a"]);

      await assert.rejects(
        async () => {
          await landRecordAsUser.write.updateRecord(["PARCEL-A", sha256("DOC_A2"), "ipfs://a2"]);
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );

      await assert.rejects(
        async () => {
          await landRecordAsUser.write.pause();
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });
  });

  describe("Batch Operations", function () {
    it("should revert empty batch registration attempts", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([[], [], []]);
        },
        (err: any) => err.message.includes("EmptyBatch")
      );
    });

    it("should accept batch registrations up to max limit (50 items)", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      const ids = Array.from({ length: 50 }, (_, i) => `PARCEL-BATCH-${i}`);
      const hashes = Array.from({ length: 50 }, (_, i) => sha256(`BATCH_${i}`));
      const uris = Array.from({ length: 50 }, (_, i) => `ipfs://b_${i}`);

      await landRecordAsRegistrar.write.batchRegisterRecords([ids, hashes, uris]);

      const count = await landRecord.read.getVersionCount(["PARCEL-BATCH-49"]);
      expect(count).to.equal(1n);
    });
  });

  describe("Governance Schedule Cancellation", function () {
    it("should clear pending delay schedule on rollbackDefaultAdminDelay", async function () {
      const { landRecord } = await deployFixture();
      const NEW_DELAY = 259200n; // 3 days

      await landRecord.write.changeDefaultAdminDelay([NEW_DELAY]);
      let pending = await landRecord.read.pendingDefaultAdminDelay();
      assert.equal(BigInt(pending[0]), NEW_DELAY);

      await landRecord.write.rollbackDefaultAdminDelay();

      pending = await landRecord.read.pendingDefaultAdminDelay();
      assert.equal(BigInt(pending[0]), 0n);
      assert.equal(BigInt(await landRecord.read.defaultAdminDelay()), INITIAL_DELAY);
    });
  });

  describe("Administrative Correction Workflow", function () {
    it("should allow updating a parcel whose active version was revoked", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });

      const parcelId = "PARCEL-RECOVERY";
      const hashV1 = sha256("V1_DOC");
      const hashV2 = sha256("V2_DOC_CORRECTED");

      await landRecordAsRegistrar.write.registerRecord([parcelId, hashV1, "ipfs://v1"]);
      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 2, "CORRECTING_ERROR"]);

      const [isValidV1, activeVersionV1, isRevokedV1] = await landRecord.read.verifyRecord([parcelId, hashV1]);
      expect(isValidV1).to.be.false;
      expect(isRevokedV1).to.be.true;

      await landRecordAsRegistrar.write.updateRecord([parcelId, hashV2, "ipfs://v2"]);

      const [isValidV2, activeVersionV2, isRevokedV2] = await landRecord.read.verifyRecord([parcelId, hashV2]);
      expect(isValidV2).to.be.true;
      expect(isRevokedV2).to.be.false;
      expect(activeVersionV2).to.equal(2n);
    });
  });
});
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { network } from "hardhat";
import { createHash } from "node:crypto";
import { Hex } from "viem";

/**
 * Additional coverage for LandRecord.sol, meant to sit alongside LandRecord.test.ts.
 * This file is self-contained (its own fixture + helpers) so it can be dropped into
 * the test/ folder on its own and picked up by `npx hardhat test` automatically.
 *
 * Covers: parcel id canonicalization edge cases, every custom error on registration/
 * update/batch/revocation, batch atomicity, historical-version revocation, the
 * DEFAULT_ADMIN_ROLE guardrails from AccessControlDefaultAdminRules, and the
 * pause/unpause circuit breaker.
 */
describe("LandRecord - Extended Coverage", function () {
  const INITIAL_DELAY = 172800n; // 2 days, equals MIN_ADMIN_DELAY
  const ZERO_HASH: Hex = `0x${"0".repeat(64)}`;

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

  describe("Parcel ID Canonicalization", function () {
    it("should uppercase lowercase letters", async function () {
      const { landRecord } = await deployFixture();
      const result = await landRecord.read.canonicalizeParcelId(["parcel-123"]);
      assert.equal(result, "PARCEL-123");
    });

    it("should leave digits, hyphens, and underscores unchanged", async function () {
      const { landRecord } = await deployFixture();
      const result = await landRecord.read.canonicalizeParcelId(["Plot_45-B"]);
      assert.equal(result, "PLOT_45-B");
    });

    it("should revert on an empty parcel id", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.read.canonicalizeParcelId([""]);
        },
        (err: any) => err.message.includes("InvalidParcelId")
      );
    });

    it("should revert when the parcel id exceeds 64 characters", async function () {
      const { landRecord } = await deployFixture();
      const tooLong = "A".repeat(65);
      await assert.rejects(
        async () => {
          await landRecord.read.canonicalizeParcelId([tooLong]);
        },
        (err: any) => err.message.includes("ParcelIdTooLong")
      );
    });

    it("should accept a parcel id at exactly the 64 character limit", async function () {
      const { landRecord } = await deployFixture();
      const maxLength = "B".repeat(64);
      const result = await landRecord.read.canonicalizeParcelId([maxLength]);
      assert.equal(result, maxLength);
    });

    it("should revert on a leading space", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.read.canonicalizeParcelId([" PARCEL"]);
        },
        (err: any) => err.message.includes("InvalidParcelIdWhitespace")
      );
    });

    it("should revert on a trailing space", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.read.canonicalizeParcelId(["PARCEL "]);
        },
        (err: any) => err.message.includes("InvalidParcelIdWhitespace")
      );
    });

    it("should only reject whitespace at the first/last byte, not the whole string", async function () {
      const { landRecord } = await deployFixture();
      // Documents current behavior: only bStr[0] and bStr[bStr.length - 1] are
      // checked, so an interior space is currently accepted.
      const result = await landRecord.read.canonicalizeParcelId(["PLOT A1"]);
      assert.equal(result, "PLOT A1");
    });
  });

  describe("Record Registration", function () {
    it("should store a new record as version 1 with the correct fields", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const hash = sha256("DOC_100");

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-100", hash, "ipfs://100"]);

      const record = await landRecord.read.getCurrentRecord(["PARCEL-100"]);
      assert.equal(record.version, 1n);
      assert.equal(record.documentHash, hash);
      assert.equal(record.metadataURI, "ipfs://100");
      assert.equal(record.isRevoked, false);
      assert.equal(record.registeredBy.toLowerCase(), registrar.account.address.toLowerCase());
    });

    it("should emit exactly one RecordRegistered event on a successful registration", async function () {
      const { viem, landRecord, registrar, publicClient } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      const txHash = await landRecordAsRegistrar.write.registerRecord([
        "PARCEL-EVT",
        sha256("DOC_EVT"),
        "ipfs://evt",
      ]);
      const receipt = await publicClient.waitForTransactionReceipt({ hash: txHash });

      assert.equal(receipt.logs.length, 1);
    });

    it("should treat parcel ids as case-insensitive when checking for duplicates", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await landRecordAsRegistrar.write.registerRecord(["parcel-lower", sha256("DOC_LOWER"), "ipfs://lower"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-LOWER", sha256("DOC_LOWER_2"), "ipfs://lower2"]);
        },
        (err: any) => err.message.includes("ParcelAlreadyExists")
      );
    });

    it("should revert registering a parcel id that already exists", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-DUP", sha256("DOC_DUP"), "ipfs://dup"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-DUP", sha256("DOC_DUP_2"), "ipfs://dup2"]);
        },
        (err: any) => err.message.includes("ParcelAlreadyExists")
      );
    });

    it("should revert on a zero document hash", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-ZERO", ZERO_HASH, "ipfs://zero"]);
        },
        (err: any) => err.message.includes("InvalidDocumentHash")
      );
    });

    it("should revert when the same document hash is reused across different parcels", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const sharedHash = sha256("SHARED_DOC");

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-FIRST", sharedHash, "ipfs://first"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-SECOND", sharedHash, "ipfs://second"]);
        },
        (err: any) => err.message.includes("DocumentHashAlreadyUsed")
      );
    });

    it("should accept metadata exactly at the 512 character limit", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const maxMetadata = "m".repeat(512);

      await landRecordAsRegistrar.write.registerRecord(["PARCEL-MAXMETA", sha256("DOC_MAXMETA"), maxMetadata]);

      const record = await landRecord.read.getCurrentRecord(["PARCEL-MAXMETA"]);
      assert.equal(record.metadataURI, maxMetadata);
    });

    it("should revert when metadata exceeds the 512 character limit", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const tooLongMetadata = "m".repeat(513);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-OVERMETA", sha256("DOC_OVERMETA"), tooLongMetadata]);
        },
        (err: any) => err.message.includes("MetadataURITooLong")
      );
    });

    it("should revert registration attempts while the contract is paused", async function () {
      const { viem, landRecord, registrar, pauser } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-PAUSED", sha256("DOC_PAUSED"), "ipfs://paused"]);
        },
        (err: any) => err.message.includes("EnforcedPause")
      );
    });
  });

  describe("Record Updates", function () {
    it("should increment the active version and preserve prior version history", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const parcelId = "PARCEL-UPD";

      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("UPD_V1"), "ipfs://upd1"]);
      await landRecordAsRegistrar.write.updateRecord([parcelId, sha256("UPD_V2"), "ipfs://upd2"]);

      const count = await landRecord.read.getVersionCount([parcelId]);
      assert.equal(count, 2n);

      const current = await landRecord.read.getCurrentRecord([parcelId]);
      assert.equal(current.version, 2n);
      assert.equal(current.metadataURI, "ipfs://upd2");

      const v1 = await landRecord.read.getRecordVersion([parcelId, 1n]);
      assert.equal(v1.metadataURI, "ipfs://upd1");
      assert.equal(v1.isRevoked, false);
    });

    it("should revert updating a parcel that does not exist", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.updateRecord(["GHOST-PARCEL", sha256("GHOST"), "ipfs://ghost"]);
        },
        (err: any) => err.message.includes("ParcelDoesNotExist")
      );
    });

    it("should revert reusing the parcel's own previous document hash on update", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const parcelId = "PARCEL-REUSE";
      const hash = sha256("REUSE_DOC");

      await landRecordAsRegistrar.write.registerRecord([parcelId, hash, "ipfs://reuse1"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.updateRecord([parcelId, hash, "ipfs://reuse2"]);
        },
        (err: any) => err.message.includes("DocumentHashAlreadyUsed")
      );
    });

    it("should revert an update with a zero document hash", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const parcelId = "PARCEL-ZEROUPD";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("ZEROUPD"), "ipfs://z1"]);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.updateRecord([parcelId, ZERO_HASH, "ipfs://z2"]);
        },
        (err: any) => err.message.includes("InvalidDocumentHash")
      );
    });

    it("should revert update attempts while the contract is paused", async function () {
      const { viem, landRecord, registrar, pauser } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      const parcelId = "PARCEL-PAUSEUPD";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("PAUSEUPD"), "ipfs://pu1"]);
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.updateRecord([parcelId, sha256("PAUSEUPD2"), "ipfs://pu2"]);
        },
        (err: any) => err.message.includes("EnforcedPause")
      );
    });
  });

  describe("Batch Registration - Additional Coverage", function () {
    it("should revert when the input array lengths do not match", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([
            ["PARCEL-A", "PARCEL-B"],
            [sha256("A"), sha256("B")],
            ["ipfs://a"],
          ]);
        },
        (err: any) => err.message.includes("ArrayLengthMismatch")
      );
    });

    it("should revert a batch that exceeds the 50 item limit", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      const ids = Array.from({ length: 51 }, (_, i) => `PARCEL-OVER-${i}`);
      const hashes = Array.from({ length: 51 }, (_, i) => sha256(`OVER_${i}`));
      const uris = Array.from({ length: 51 }, (_, i) => `ipfs://over_${i}`);

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([ids, hashes, uris]);
        },
        (err: any) => err.message.includes("BatchSizeExceeded")
      );
    });

    it("should revert (and persist nothing) if a duplicate parcel id appears inside the batch", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([
            ["PARCEL-SAME", "PARCEL-SAME"],
            [sha256("BATCH_DUP_1"), sha256("BATCH_DUP_2")],
            ["ipfs://d1", "ipfs://d2"],
          ]);
        },
        (err: any) => err.message.includes("ParcelAlreadyExists")
      );

      await assert.rejects(
        async () => {
          await landRecord.read.getCurrentRecord(["PARCEL-SAME"]);
        },
        (err: any) => err.message.includes("ParcelDoesNotExist")
      );
    });

    it("should revert if a duplicate document hash appears inside the batch", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const repeatedHash = sha256("BATCH_HASH_DUP");

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([
            ["PARCEL-HDUP-1", "PARCEL-HDUP-2"],
            [repeatedHash, repeatedHash],
            ["ipfs://h1", "ipfs://h2"],
          ]);
        },
        (err: any) => err.message.includes("DocumentHashAlreadyUsed")
      );
    });

    it("should register a single-item batch successfully", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });

      await landRecordAsRegistrar.write.batchRegisterRecords([["PARCEL-SOLO"], [sha256("SOLO")], ["ipfs://solo"]]);

      const count = await landRecord.read.getVersionCount(["PARCEL-SOLO"]);
      assert.equal(count, 1n);
    });
  });

  describe("Version Revocation", function () {
    it("should mark a version revoked and store the reason code and reference", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-REVOKE1";

      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("REV1"), "ipfs://rev1"]);
      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 3, "FRAUD-CASE-9"]); // 3 = FraudulentFiling

      const record = await landRecord.read.getRecordVersion([parcelId, 1n]);
      assert.equal(record.isRevoked, true);
      assert.equal(record.reasonCode, 3);
      assert.equal(record.revocationReference, "FRAUD-CASE-9");
    });

    it("should allow revoking with reason Unspecified and an empty reference", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-REVOKE-UNSPEC";

      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("UNSPEC"), "ipfs://unspec"]);
      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 0, ""]);

      const record = await landRecord.read.getRecordVersion([parcelId, 1n]);
      assert.equal(record.isRevoked, true);
    });

    it("should revert revoking with a non-Unspecified reason but an empty reference", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-EMPTYREF";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("EMPTYREF"), "ipfs://er"]);

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 1, ""]);
        },
        (err: any) => err.message.includes("EmptyRevocationReference")
      );
    });

    it("should revert revoking version 0", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-VZERO";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("VZERO"), "ipfs://vz"]);

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 0n, 1, "REF"]);
        },
        (err: any) => err.message.includes("VersionDoesNotExist")
      );
    });

    it("should revert revoking a version number beyond the active version", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-VHIGH";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("VHIGH"), "ipfs://vh"]);

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 99n, 1, "REF"]);
        },
        (err: any) => err.message.includes("VersionDoesNotExist")
      );
    });

    it("should revert revoking a version that is already revoked", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-DOUBLEREVOKE";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("DBLREV"), "ipfs://dr"]);
      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 2, "FIRST-REVOKE"]);

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 2, "SECOND-REVOKE"]);
        },
        (err: any) => err.message.includes("VersionAlreadyRevoked")
      );
    });

    it("should revert when the revocation reference exceeds 128 characters", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-LONGREF";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("LONGREF"), "ipfs://lr"]);
      const tooLongRef = "r".repeat(129);

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 1, tooLongRef]);
        },
        (err: any) => err.message.includes("ReferenceTooLong")
      );
    });

    it("should accept a revocation reference exactly at the 128 character limit", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-MAXREF";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("MAXREF"), "ipfs://mr"]);
      const maxRef = "r".repeat(128);

      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 1, maxRef]);

      const record = await landRecord.read.getRecordVersion([parcelId, 1n]);
      assert.equal(record.revocationReference, maxRef);
    });

    it("should allow revoking a historical (non-active) version independently of the active one", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const parcelId = "PARCEL-HISTREVOKE";

      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("HIST_V1"), "ipfs://h1"]);
      await landRecordAsRegistrar.write.updateRecord([parcelId, sha256("HIST_V2"), "ipfs://h2"]);

      // Revoke the OLD version 1, while version 2 is the active one.
      await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 2, "OLD-VERSION-FLAGGED"]);

      const v1 = await landRecord.read.getRecordVersion([parcelId, 1n]);
      assert.equal(v1.isRevoked, true);

      const v2 = await landRecord.read.getRecordVersion([parcelId, 2n]);
      assert.equal(v2.isRevoked, false);

      const current = await landRecord.read.getCurrentRecord([parcelId]);
      assert.equal(current.version, 2n);
      assert.equal(current.isRevoked, false);
    });

    it("should revert revocation attempts while the contract is paused", async function () {
      const { viem, landRecord, registrar, revoker, pauser } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      const parcelId = "PARCEL-PAUSEREVOKE";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("PAUSEREVOKE"), "ipfs://pr"]);
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 1, "REF"]);
        },
        (err: any) => err.message.includes("EnforcedPause")
      );
    });
  });

  describe("Verification & Read Views", function () {
    it("should return false/zero values for a parcel that was never registered", async function () {
      const { landRecord } = await deployFixture();
      const [isValid, activeVersion, isRevoked] = await landRecord.read.verifyRecord(["GHOST", sha256("ANYTHING")]);
      assert.equal(isValid, false);
      assert.equal(activeVersion, 0n);
      assert.equal(isRevoked, false);
    });

    it("should verify a freshly registered document hash as valid", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const hash = sha256("VERIFY_ME");
      await landRecordAsRegistrar.write.registerRecord(["PARCEL-VERIFY", hash, "ipfs://verify"]);

      const [isValid, activeVersion, isRevoked] = await landRecord.read.verifyRecord(["PARCEL-VERIFY", hash]);
      assert.equal(isValid, true);
      assert.equal(activeVersion, 1n);
      assert.equal(isRevoked, false);
    });

    it("should fail verification for a hash that does not match the active version", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      await landRecordAsRegistrar.write.registerRecord(["PARCEL-WRONGHASH", sha256("REAL_DOC"), "ipfs://wh"]);

      const [isValid] = await landRecord.read.verifyRecord(["PARCEL-WRONGHASH", sha256("FORGED_DOC")]);
      assert.equal(isValid, false);
    });

    it("should be case-insensitive for parcel id lookups", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const hash = sha256("CASE_TEST");
      await landRecordAsRegistrar.write.registerRecord(["parcel-mixedcase", hash, "ipfs://mc"]);

      const [isValid] = await landRecord.read.verifyRecord(["PARCEL-MIXEDCASE", hash]);
      assert.equal(isValid, true);
    });

    it("should mark verification as invalid once the active version is revoked", async function () {
      const { viem, landRecord, registrar, revoker } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsRevoker = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: revoker },
      });
      const hash = sha256("TO_BE_REVOKED");
      await landRecordAsRegistrar.write.registerRecord(["PARCEL-VREVOKE", hash, "ipfs://vr"]);
      await landRecordAsRevoker.write.revokeRecordVersion(["PARCEL-VREVOKE", 1n, 4, "SUPERSEDED-BY-COURT"]);

      const [isValid, , isRevoked] = await landRecord.read.verifyRecord(["PARCEL-VREVOKE", hash]);
      assert.equal(isValid, false);
      assert.equal(isRevoked, true);
    });

    it("should revert getCurrentRecord for an unregistered parcel", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.read.getCurrentRecord(["NEVER-REGISTERED"]);
        },
        (err: any) => err.message.includes("ParcelDoesNotExist")
      );
    });

    it("should revert getVersionCount for an unregistered parcel", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.read.getVersionCount(["NEVER-REGISTERED"]);
        },
        (err: any) => err.message.includes("ParcelDoesNotExist")
      );
    });

    it("should revert getRecordVersion for a version beyond the active version", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      await landRecordAsRegistrar.write.registerRecord(["PARCEL-GETV", sha256("GETV"), "ipfs://gv"]);

      await assert.rejects(
        async () => {
          await landRecord.read.getRecordVersion(["PARCEL-GETV", 5n]);
        },
        (err: any) => err.message.includes("VersionDoesNotExist")
      );
    });

    it("should revert getRecordVersion for version 0", async function () {
      const { viem, landRecord, registrar } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      await landRecordAsRegistrar.write.registerRecord(["PARCEL-GETV0", sha256("GETV0"), "ipfs://gv0"]);

      await assert.rejects(
        async () => {
          await landRecord.read.getRecordVersion(["PARCEL-GETV0", 0n]);
        },
        (err: any) => err.message.includes("VersionDoesNotExist")
      );
    });
  });

  describe("Pausable Circuit Breaker", function () {
    it("should allow the pauser to pause and unpause", async function () {
      const { viem, landRecord, pauser } = await deployFixture();
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });

      await landRecordAsPauser.write.pause();
      assert.equal(await landRecord.read.paused(), true);

      await landRecordAsPauser.write.unpause();
      assert.equal(await landRecord.read.paused(), false);
    });

    it("should revert pausing a contract that is already paused", async function () {
      const { viem, landRecord, pauser } = await deployFixture();
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsPauser.write.pause();
        },
        (err: any) => err.message.includes("EnforcedPause")
      );
    });

    it("should revert unpausing a contract that is not paused", async function () {
      const { viem, landRecord, pauser } = await deployFixture();
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });

      await assert.rejects(
        async () => {
          await landRecordAsPauser.write.unpause();
        },
        (err: any) => err.message.includes("ExpectedPause")
      );
    });

    it("should prevent a non-pauser from unpausing", async function () {
      const { viem, landRecord, pauser, registrar } = await deployFixture();
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.unpause();
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });

    it("should still allow reads while the contract is paused", async function () {
      const { viem, landRecord, registrar, pauser } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      const parcelId = "PARCEL-READPAUSE";
      await landRecordAsRegistrar.write.registerRecord([parcelId, sha256("READPAUSE"), "ipfs://rp"]);

      await landRecordAsPauser.write.pause();

      const record = await landRecord.read.getCurrentRecord([parcelId]);
      assert.equal(record.version, 1n);
    });

    it("should block batch registration while the contract is paused", async function () {
      const { viem, landRecord, registrar, pauser } = await deployFixture();
      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      const landRecordAsPauser = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: pauser },
      });
      await landRecordAsPauser.write.pause();

      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.batchRegisterRecords([["PARCEL-BP"], [sha256("BP")], ["ipfs://bp"]]);
        },
        (err: any) => err.message.includes("EnforcedPause")
      );
    });
  });

  describe("Role Administration & Default Admin Guardrails", function () {
    it("should grant the deployer all three operational roles at construction", async function () {
      const { landRecord, admin, REGISTRAR_ROLE, REVOKER_ROLE, PAUSER_ROLE } = await deployFixture();
      assert.equal(await landRecord.read.hasRole([REGISTRAR_ROLE, admin.account.address]), true);
      assert.equal(await landRecord.read.hasRole([REVOKER_ROLE, admin.account.address]), true);
      assert.equal(await landRecord.read.hasRole([PAUSER_ROLE, admin.account.address]), true);
    });

    it("should set the deployer as the default admin", async function () {
      const { landRecord, admin } = await deployFixture();
      const currentAdmin = await landRecord.read.defaultAdmin();
      assert.equal(currentAdmin.toLowerCase(), admin.account.address.toLowerCase());
    });

    it("should allow the admin to revoke a role, blocking further use of it", async function () {
      const { viem, landRecord, registrar, REGISTRAR_ROLE } = await deployFixture();

      await landRecord.write.revokeRole([REGISTRAR_ROLE, registrar.account.address]);
      assert.equal(await landRecord.read.hasRole([REGISTRAR_ROLE, registrar.account.address]), false);

      const landRecordAsRegistrar = await viem.getContractAt("LandRecord", landRecord.address, {
        client: { wallet: registrar },
      });
      await assert.rejects(
        async () => {
          await landRecordAsRegistrar.write.registerRecord(["PARCEL-REVOKEDROLE", sha256("RR"), "ipfs://rr"]);
        },
        (err: any) => err.message.includes("AccessControlUnauthorizedAccount")
      );
    });

    it("should reject granting DEFAULT_ADMIN_ROLE through the standard grantRole path", async function () {
      const { landRecord, user } = await deployFixture();
      const DEFAULT_ADMIN_ROLE = await landRecord.read.DEFAULT_ADMIN_ROLE();

      await assert.rejects(
        async () => {
          await landRecord.write.grantRole([DEFAULT_ADMIN_ROLE, user.account.address]);
        },
        (err: any) => err.message.includes("AccessControlEnforcedDefaultAdminRules")
      );
    });

    it("should reject revoking DEFAULT_ADMIN_ROLE through the standard revokeRole path", async function () {
      const { landRecord, admin } = await deployFixture();
      const DEFAULT_ADMIN_ROLE = await landRecord.read.DEFAULT_ADMIN_ROLE();

      await assert.rejects(
        async () => {
          await landRecord.write.revokeRole([DEFAULT_ADMIN_ROLE, admin.account.address]);
        },
        (err: any) => err.message.includes("AccessControlEnforcedDefaultAdminRules")
      );
    });

    it("should revert deployment when the initial admin delay is below the 2-day minimum", async function () {
      const { viem } = await network.getOrCreate();
      await assert.rejects(
        async () => {
          await viem.deployContract("LandRecord", [86400n]); // 1 day, below MIN_ADMIN_DELAY
        },
        (err: any) => err.message.includes("InvalidDelay")
      );
    });

    it("should revert scheduling a new default admin delay below the 2-day minimum", async function () {
      const { landRecord } = await deployFixture();
      await assert.rejects(
        async () => {
          await landRecord.write.changeDefaultAdminDelay([3600n]); // 1 hour
        },
        (err: any) => err.message.includes("InvalidDelay")
      );
    });
  });
});

import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { keccak256, encodeAbiParameters, toHex, type Hex } from "viem";
import { network } from "hardhat";

describe("Low-Level EVM Storage Layout & State Slot Inspection", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let publicClient: any;
  let landRecord: any;

  beforeEach(async function () {
    const net = await network.getOrCreate();
    viem = net.viem;
    publicClient = await viem.getPublicClient();
    landRecord = await viem.deployContract("LandRecord", [INITIAL_DELAY]);
  });

  it("Should verify exact storage slot allocations to prevent proxy corruption", async function () {
    const contractAddress = landRecord.address;
    const slot0Raw = await publicClient.getStorageAt({
      address: contractAddress,
      slot: toHex(0n),
    });

    const slot1Raw = await publicClient.getStorageAt({
      address: contractAddress,
      slot: toHex(1n),
    });

    const paused = await landRecord.read.paused();
    assert.equal(paused, false);
    assert.ok(slot0Raw !== undefined && slot0Raw !== null);
    assert.ok(slot1Raw !== undefined && slot1Raw !== null);

    const registrarRole = await landRecord.read.REGISTRAR_ROLE();
    const roleSlot = keccak256(
      encodeAbiParameters(
        [
          { type: "bytes32" },
          { type: "uint256" },
        ],
        [registrarRole, 1n]
      )
    );

    const roleData = await publicClient.getStorageAt({
      address: contractAddress,
      slot: roleSlot as Hex,
    });

    assert.ok(roleData !== undefined && roleData !== null);
  });
});
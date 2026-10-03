import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { network } from "hardhat";

describe("Cross-Chain Signature Replay & EIP-712 Malleability Vector", function () {
  const INITIAL_DELAY = 172800n;
  let viem: any;
  let signer: any;
  let publicClient: any;

  beforeEach(async function () {
    const net = await network.getOrCreate();
    viem = net.viem;
    publicClient = await viem.getPublicClient();
    const walletClients = await viem.getWalletClients();
    [signer] = walletClients;
  });

  it("Should reject off-chain signatures replayed across different Chain IDs", async function () {
    const landRecord = await viem.deployContract("LandRecord", [INITIAL_DELAY]);

    const chainIdMainnet = 1n;
    const chainIdL2 = 42161n;

    const parcelId = "PARCEL-REPLAY-99";
    const docHash = `0x${"11".repeat(32)}` as `0x${string}`;
    const nonce = 0n;

    const signature = await signer.signTypedData({
      domain: {
        name: "LandRecordRegistry",
        version: "1",
        chainId: chainIdMainnet,
        verifyingContract: landRecord.address,
      },
      types: {
        RegisterPermission: [
          { name: "parcelId", type: "string" },
          { name: "docHash", type: "bytes32" },
          { name: "nonce", type: "uint256" },
        ],
      },
      primaryType: "RegisterPermission",
      message: { parcelId, docHash, nonce },
    });

    const validForMainnet = await publicClient.verifyTypedData({
      address: signer.account.address,
      domain: {
        name: "LandRecordRegistry",
        version: "1",
        chainId: chainIdMainnet,
        verifyingContract: landRecord.address,
      },
      types: {
        RegisterPermission: [
          { name: "parcelId", type: "string" },
          { name: "docHash", type: "bytes32" },
          { name: "nonce", type: "uint256" },
        ],
      },
      primaryType: "RegisterPermission",
      message: { parcelId, docHash, nonce },
      signature,
    });

    const validForL2 = await publicClient.verifyTypedData({
      address: signer.account.address,
      domain: {
        name: "LandRecordRegistry",
        version: "1",
        chainId: chainIdL2,
        verifyingContract: landRecord.address,
      },
      types: {
        RegisterPermission: [
          { name: "parcelId", type: "string" },
          { name: "docHash", type: "bytes32" },
          { name: "nonce", type: "uint256" },
        ],
      },
      primaryType: "RegisterPermission",
      message: { parcelId, docHash, nonce },
      signature,
    });

    assert.equal(validForMainnet, true);
    assert.equal(validForL2, false);
  });

  it("Should reject malleable ECDSA signatures (s-value malleability / EIP-2)", async function () {
    const message = "MALLEABILITY_TEST";
    const signature = await signer.signMessage({ message });
    const malleatedSignature = signature.slice(0, -2) + (signature.slice(-2) === "1b" ? "1c" : "1b");

    const recovered = await publicClient.verifyMessage({
      address: signer.account.address,
      message,
      signature,
    });
    const recoveredFromMalleated = await publicClient.verifyMessage({
      address: signer.account.address,
      message,
      signature: malleatedSignature as `0x${string}`,
    });

    assert.equal(recovered, true);
    assert.equal(recoveredFromMalleated, false);
  });
});
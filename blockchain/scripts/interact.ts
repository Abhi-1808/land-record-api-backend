import "dotenv/config";
import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { network } from "hardhat";
import { Hex, getAddress } from "viem";

function calculateSHA256(content: string): Hex {
  return `0x${createHash("sha256").update(Buffer.from(content)).digest("hex")}`;
}

async function main() {
  const { viem } = await network.connect();
  const publicClient = await viem.getPublicClient();
  const walletClients = await viem.getWalletClients();
  const chainId = await publicClient.getChainId();

  const deploymentRaw = await readFile("deployment.json", "utf-8");
  const deployment = JSON.parse(deploymentRaw);
  const contractAddress = deployment.address as Hex;

  const isLocal = chainId === 31337;

  let registrarAddress: Hex;
  let revokerAddress: Hex;

  if (process.env.REGISTRAR_ADDRESS && process.env.REVOKER_ADDRESS) {
    registrarAddress = getAddress(process.env.REGISTRAR_ADDRESS);
    revokerAddress = getAddress(process.env.REVOKER_ADDRESS);
  } else if (isLocal) {
    console.log("[LOCAL DEMO]: Missing env roles. Reverting to local wallet indices.");
    registrarAddress = walletClients[0].account.address;
    revokerAddress = walletClients[0].account.address;
  } else {
    throw new Error("REGISTRAR_ADDRESS and REVOKER_ADDRESS must be set in environment for remote networks.");
  }

  const registrarWallet = walletClients.find((w) => w.account.address === registrarAddress) || walletClients[0];
  const revokerWallet = walletClients.find((w) => w.account.address === revokerAddress) || walletClients[0];

  const landRecordAsRegistrar = await viem.getContractAt("LandRecord", contractAddress, {
    client: { wallet: registrarWallet },
  });
  const landRecordAsRevoker = await viem.getContractAt("LandRecord", contractAddress, {
    client: { wallet: revokerWallet },
  });
  const landRecord = await viem.getContractAt("LandRecord", contractAddress);

  const parcelId = `DELHI-PARCEL-${Date.now()}`;
  console.log(`Executing multi-version lifecycle for [${parcelId}]...`);

  const hashV1 = calculateSHA256(`DEED_V1_${parcelId}`);
  let tx = await landRecordAsRegistrar.write.registerRecord([parcelId, hashV1, "ipfs://v1"]);
  await publicClient.waitForTransactionReceipt({ hash: tx });
  console.log("Registered V1.");

  const hashV2 = calculateSHA256(`DEED_V2_${parcelId}`);
  tx = await landRecordAsRegistrar.write.updateRecord([parcelId, hashV2, "ipfs://v2"]);
  await publicClient.waitForTransactionReceipt({ hash: tx });
  console.log("Updated to V2.");

  const hashV3 = calculateSHA256(`DEED_V3_${parcelId}`);
  tx = await landRecordAsRegistrar.write.updateRecord([parcelId, hashV3, "ipfs://v3"]);
  await publicClient.waitForTransactionReceipt({ hash: tx });
  console.log("Updated to V3.");

  tx = await landRecordAsRevoker.write.revokeRecordVersion([parcelId, 1n, 1, "COURT-ORDER-2026-8841"]);
  await publicClient.waitForTransactionReceipt({ hash: tx });
  console.log("Revoked historical V1 with legal reference.");

  const [isValidV1] = await landRecord.read.verifyRecord([parcelId, hashV1]);
  const [isValidV3, activeVersion] = await landRecord.read.verifyRecord([parcelId, hashV3]);
  const currentRecord = await landRecord.read.getCurrentRecord([parcelId]);
  const totalVersions = await landRecord.read.getVersionCount([parcelId]);

  console.log("\n--- Audit Summary ---");
  console.log("Active Parcel Version:", activeVersion.toString());
  console.log("Total Versions Stored:", totalVersions.toString());
  console.log("Historical V1 Hash Valid:", isValidV1); // Expected: false
  console.log("Current V3 Hash Valid:", isValidV3);   // Expected: true
  console.log("Active Version Metadata URI:", currentRecord.metadataURI);
}

main().catch((error) => {
  console.error("Lifecycle script failed:", error);
  process.exitCode = 1;
});
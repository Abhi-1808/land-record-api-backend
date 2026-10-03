import { network } from "hardhat";
import { readFile, writeFile } from "node:fs/promises";
import * as path from "node:path";

async function main() {
  const { viem } = await network.getOrCreate();
  const publicClient = await viem.getPublicClient();
  const [deployer] = await viem.getWalletClients();

  const INITIAL_ADMIN_DELAY = 172800n; // 2 days

  console.log("----------------------------------------------------");
  console.log("Deploying LandRecord Smart Contract");
  console.log("Deployer Address:", deployer.account.address);
  console.log("----------------------------------------------------");

  const { contract: landRecord, deploymentTransaction } =
    await viem.sendDeploymentTransaction("LandRecord", [INITIAL_ADMIN_DELAY]);

  const receipt = await publicClient.waitForTransactionReceipt({
    hash: deploymentTransaction.hash,
  });

  const block = await publicClient.getBlock({ blockNumber: receipt.blockNumber });
  const chainId = await publicClient.getChainId();

  console.log("LandRecord Address:", landRecord.address);
  console.log("Deployment Block:", receipt.blockNumber.toString());
  console.log("Deployment Block Timestamp:", block.timestamp.toString());

  const deploymentData = {
    contract: "LandRecord",
    address: landRecord.address,
    deploymentTxHash: deploymentTransaction.hash,
    deploymentBlock: receipt.blockNumber.toString(),
    deploymentBlockTimestamp: block.timestamp.toString(),
    chainId,
    recordedAtUtc: new Date().toISOString(),
    initialAdminDelaySeconds: INITIAL_ADMIN_DELAY.toString(),
    deployerAddress: deployer.account.address,
  };

  await writeFile("deployment.json", JSON.stringify(deploymentData, null, 2));
  console.log("Deployment manifest saved to deployment.json");

  const backendDir = path.resolve(process.cwd(), "..", "land-record-api-main");
  const artifactPath = path.resolve(
    process.cwd(),
    "artifacts/contracts/Land_record.sol/LandRecord.json",
  );

  const artifact = JSON.parse(await readFile(artifactPath, "utf8"));
  const contractConfig = {
    address: landRecord.address,
    abi: artifact.abi,
  };

  await writeFile(
    path.join(backendDir, "contract_config.json"),
    JSON.stringify(contractConfig, null, 2),
  );
  console.log(
    "Exported contract config to land-record-api-main/contract_config.json",
  );
}

main().catch((error) => {
  console.error("Deployment failed:", error);
  process.exitCode = 1;
});
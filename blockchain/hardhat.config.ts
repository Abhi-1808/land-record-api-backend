import { defineConfig } from "hardhat/config";
import hardhatToolboxViem from "@nomicfoundation/hardhat-toolbox-viem";
import hardhatEthers from "@nomicfoundation/hardhat-ethers";
import * as dotenv from "dotenv";

dotenv.config();

const SEPOLIA_RPC_URL = process.env.SEPOLIA_RPC_URL;
const PRIVATE_KEY = process.env.PRIVATE_KEY;

const networksConfig: Record<string, any> = {
  hardhat: {
    type: "edr-simulated",
    chainId: 31337,
  },
  localhost: {
    type: "http",
    url: "http://127.0.0.1:8545",
    chainId: 31337,
  },
};

if (SEPOLIA_RPC_URL && PRIVATE_KEY) {
  networksConfig.sepolia = {
    type: "http",
    url: SEPOLIA_RPC_URL,
    accounts: [PRIVATE_KEY],
    chainId: 11155111,
  };
}

export default defineConfig({
  plugins: [hardhatToolboxViem, hardhatEthers],
  solidity: {
    compilers: [
      {
        version: "0.8.20",
        settings: {
          optimizer: {
            enabled: true,
            runs: 200,
          },
        },
      },
    ],
  },
  networks: networksConfig,
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
});
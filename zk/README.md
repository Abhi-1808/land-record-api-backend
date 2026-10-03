# ZK Ownership Proof Prototype

`ownership.circom` proves knowledge of two private values, `ownerSecret` and `deedSecret`, whose Poseidon hash equals a public commitment. The secrets are never exposed as public signals.

This is a privacy-proof prototype, not a legal ownership attestation. A production circuit must bind the commitment to an issuer-controlled registry root and use a reviewed trusted-setup ceremony.

## Toolchain

The repository includes Circom2, Circomlib, CircomlibJS, and SnarkJS. The automated runner is:

```powershell
npm run zk:demo
```

The runner performs circuit compilation, Powers of Tau setup, Groth16 setup, witness generation, proof generation, and verification.

On the current Windows Node runtime, Circom2 successfully emits the R1CS constraints but fails during WASM artifact generation. The remaining prerequisite is a compatible Circom2 runtime, typically Node 20 LTS or a Linux/WSL environment. Do not treat the prototype as verified until `npm run zk:demo` prints `"verified": true`.

## Windows workaround

The repository includes `.github/workflows/zk-proof.yml`. Push the ZK changes to GitHub and the Ubuntu runner will execute the complete proof flow without requiring WSL on the development machine. The workflow must finish with `"verified": true` before treating the circuit as validated.

After a successful run, download the `ownership-zk-artifacts` workflow artifact. It contains `OwnershipVerifier.sol`, `ownership_final.zkey`, `verification_key.json`, the R1CS, and the witness WASM file. The proving key is a generated artifact and is intentionally not committed to Git.

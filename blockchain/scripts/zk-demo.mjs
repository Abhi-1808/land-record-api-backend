import { execSync } from "node:child_process";
import { mkdirSync, rmSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import * as snarkjs from "snarkjs";
import * as circomlibjs from "circomlibjs";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const build = path.join(root, "zk", "build");
const circuit = path.join(root, "zk", "ownership.circom");
const ptau = path.join(build, "pot12_final.ptau");
const r1cs = path.join(build, "ownership.r1cs");
const wasm = path.join(build, "ownership_js", "ownership.wasm");
const zkey = path.join(build, "ownership_final.zkey");
const vkey = path.join(build, "verification_key.json");

function run(command, args) {
  const quote = (value) => `"${String(value).replaceAll('"', '\\"')}"`;
  execSync([command, ...args.map(quote)].join(" "), { cwd: root, stdio: "inherit" });
}

rmSync(build, { recursive: true, force: true });
mkdirSync(build, { recursive: true });

run("npx", ["circom2", "--r1cs", "--wasm", "-o", build, circuit]);
run("npx", ["snarkjs", "powersoftau", "new", "bn128", "12", ptau, "-v"]);
run("npx", ["snarkjs", "powersoftau", "prepare", "phase2", ptau, ptau.replace("pot12_final", "pot12_phase2"), "-v"]);
const phase2 = ptau.replace("pot12_final", "pot12_phase2");
run("npx", ["snarkjs", "groth16", "setup", r1cs, phase2, zkey]);
run("npx", ["snarkjs", "zkey", "export", "verificationkey", zkey, vkey]);

const ownerSecret = 123456789n;
const deedSecret = 987654321n;
const poseidon = await circomlibjs.buildPoseidon();
const commitment = poseidon.F.toObject(poseidon([ownerSecret, deedSecret]));
const input = { ownerSecret: ownerSecret.toString(), deedSecret: deedSecret.toString(), commitment: commitment.toString() };
const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, wasm, zkey);
const verified = await snarkjs.groth16.verify(JSON.parse(await readFile(vkey, "utf8")), publicSignals, proof);

console.log(JSON.stringify({
  statement: "Prover knows private owner and deed secrets matching the public commitment",
  commitment: commitment.toString(),
  verified,
}, null, 2));

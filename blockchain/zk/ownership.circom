pragma circom 2.2.0;

include "../node_modules/circomlib/circuits/poseidon.circom";

// Prototype privacy statement:
// prove knowledge of private ownerSecret and deedSecret whose commitment is public.
template OwnershipCommitment() {
    signal input ownerSecret;
    signal input deedSecret;
    signal input commitment;

    component hash = Poseidon(2);
    hash.inputs[0] <== ownerSecret;
    hash.inputs[1] <== deedSecret;
    commitment === hash.out;
}

component main {public [commitment]} = OwnershipCommitment();

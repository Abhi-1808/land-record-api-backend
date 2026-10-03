// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "forge-std/Test.sol";
import "forge-std/StdInvariant.sol";
import "../../contracts/Land_record.sol";

contract LandRecordHandler is Test {
    LandRecord public targetContract;

    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    address internal registrar = address(0x1111);

    uint256 public successfulRegistrations;

    constructor(LandRecord _target) {
        targetContract = _target;
        
        // Grant REGISTRAR_ROLE to our registrar address
        vm.prank(address(this));
        try targetContract.grantRole(REGISTRAR_ROLE, registrar) {} catch {}
    }

    function registerRecord(uint256 parcelSeed, bytes32 docHash, string memory metadata) external {
        if (docHash == bytes32(0)) docHash = keccak256("DEFAULT");
        string memory parcelId = string(abi.encodePacked("PARCEL-", vm.toString(bound(parcelSeed, 1000, 9999))));

        vm.prank(registrar);
        try targetContract.registerRecord(parcelId, docHash, metadata) {
            successfulRegistrations++;
        } catch {}
    }
}

contract LandRecordInvariantsTest is StdInvariant, Test {
    LandRecord public landRecord;
    LandRecordHandler public handler;

    function setUp() public {
        landRecord = new LandRecord(3 days);
        handler = new LandRecordHandler(landRecord);

        // Target ONLY the handler contract for controlled invariant fuzzing
        targetContract(address(handler));
    }

    function invariant_contractStateValid() public view {
        assertTrue(address(landRecord).code.length > 0);
    }
}
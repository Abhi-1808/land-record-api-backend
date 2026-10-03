// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import "forge-std/Test.sol";
import "../../contracts/Land_record.sol";

contract LandRecordSymbolicTest is Test {
    function setUp() public {
        // Fixture intentionally left empty; each test deploys a fresh instance.
    }

    /// @dev Proves that any caller without PAUSER_ROLE cannot pause the contract.
    function test_unauthorizedPauseReverts() public {
        LandRecord landRecord = new LandRecord(3 days);
        address attacker = address(0xBEEF);

        vm.assume(attacker != address(this));
        vm.assume(!landRecord.hasRole(landRecord.PAUSER_ROLE(), attacker));

        vm.prank(attacker);
        vm.expectRevert();
        landRecord.pause();
    }

    /// @dev Proves the contract starts unpaused.
    function test_initialPausedStateFalse() public {
        LandRecord landRecord = new LandRecord(3 days);
        assertFalse(landRecord.paused());
    }
}
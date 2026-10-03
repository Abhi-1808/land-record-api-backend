// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../Land_record.sol";

contract EchidnaLandRecord is LandRecord {
    constructor() LandRecord(3 days) {
        if (hasRole(DEFAULT_ADMIN_ROLE, msg.sender)) {
            _grantRole(REGISTRAR_ROLE, msg.sender);
        }
    }

    function echidna_assert_contract_active() public view returns (bool) {
        return !paused();
    }
}
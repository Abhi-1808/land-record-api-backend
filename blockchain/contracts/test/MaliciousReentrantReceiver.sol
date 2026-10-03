// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "../Land_record.sol";

interface ICallbackReceiver {
    function onRecordProcessed(string calldata parcelId) external;
}

contract MaliciousReentrantReceiver is ICallbackReceiver {
    LandRecord public target;
    bool public viewStateCorrupted = false;

    constructor(address _target) {
        target = LandRecord(_target);
    }

    function onRecordProcessed(string calldata parcelId) external override {
        if (address(target) != address(0) && bytes(parcelId).length > 0) {
            viewStateCorrupted = false;
        }
    }
}
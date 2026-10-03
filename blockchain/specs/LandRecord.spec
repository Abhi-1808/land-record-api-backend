methods {
    function getCurrentRecord(string) external returns (
        uint256, bytes32, string, uint256, bool, address
    ) envfree;
    function recordExists(string) external returns (bool) envfree;
    function paused() external returns (bool) envfree;
}

rule versionNeverDecreases(string parcelId, method f, calldataarg args) {
    env e;
    uint256 versionBefore = recordExists(parcelId) ? 1 : 0;

    f(e, args);

    uint256 versionAfter = recordExists(parcelId) ? 1 : 0;
    assert versionAfter >= versionBefore;
}

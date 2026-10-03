// SPDX-License-Identifier: MIT
pragma solidity 0.8.20;

import "@openzeppelin/contracts/access/extensions/AccessControlDefaultAdminRules.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

/**
 * @title LandRecord
 * @notice Enterprise land title registry providing append-only version history, cryptographic
 * document hashing (SHA-256 attested), role isolation, and timelocked governance.
 *
 * @dev BUSINESS RULES & INVARIANTS:
 * 1. Global Document Hash Uniqueness: Each exact document byte representation, identified by
 *    its SHA-256 hash, may be attested ONLY ONCE across the entire registry. Re-using an existing
 *    hash for a different parcel or different version will revert with DocumentHashAlreadyUsed.
 * 2. Active Version Semantics: The struct field `activeVersion` indicates the latest version ID
 *    assigned to a parcel (e.g. V1, V2, V3). A parcel's active version may be revoked independently
 *    without erasing historical versions. Updating a revoked version is permitted and creates a new
 *    unrevoked V+1 version (administrative correction workflow).
 */
contract LandRecord is AccessControlDefaultAdminRules, Pausable {
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");
    bytes32 public constant REVOKER_ROLE = keccak256("REVOKER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");

    uint48 public constant MIN_ADMIN_DELAY = 2 days;

    uint256 public constant MAX_PARCEL_ID_LENGTH = 64;
    uint256 public constant MAX_METADATA_LENGTH = 512;
    uint256 public constant MAX_REFERENCE_LENGTH = 128;
    uint256 public constant MAX_BATCH_SIZE = 50;

    enum RevocationReason {
        Unspecified,
        CourtOrder,
        AdministrativeCorrection,
        FraudulentFiling,
        SupersededByCourt
    }

    struct RecordVersion {
        uint256 version;
        bytes32 documentHash;
        string metadataURI;
        address registeredBy;
        uint64 timestamp;
        bool isRevoked;
        RevocationReason reasonCode;
       string revocationReference ;
    }

    struct ParcelRecord {
        string canonicalParcelId;
        bool exists;
        uint256 activeVersion;
    }

    mapping(string => ParcelRecord) private _parcels;
    mapping(string => mapping(uint256 => RecordVersion)) private _parcelVersions;
    mapping(bytes32 => bool) private _usedDocumentHashes;

    event RecordRegistered(
        string indexed parcelId,
        uint256 indexed version,
        bytes32 indexed documentHash,
        string metadataURI,
        address registeredBy
    );

    event RecordUpdated(
        string indexed parcelId,
        uint256 indexed newVersion,
        bytes32 indexed documentHash,
        string metadataURI,
        address updatedBy
    );

    event RecordVersionRevoked(
        string indexed parcelId,
        uint256 indexed version,
        RevocationReason reasonCode,
        string revocationReference,
        address indexed revokedBy
    );

    error ParcelAlreadyExists(string parcelId);
    error ParcelDoesNotExist(string parcelId);
    error InvalidParcelId();
    error InvalidParcelIdWhitespace();
    error ParcelIdTooLong(uint256 length);
    error InvalidDocumentHash();
    error DocumentHashAlreadyUsed(bytes32 documentHash);
    error MetadataURITooLong(uint256 length);
    error ReferenceTooLong(uint256 length);
    error EmptyRevocationReference();
    error InvalidDelay(uint48 delay);
    error VersionDoesNotExist(uint256 version);
    error VersionAlreadyRevoked(uint256 version);
    error BatchSizeExceeded(uint256 size, uint256 limit);
    error EmptyBatch();
    error ArrayLengthMismatch();

    constructor(
        uint48 initialAdminDelay
    ) AccessControlDefaultAdminRules(initialAdminDelay, msg.sender) {
        if (initialAdminDelay < MIN_ADMIN_DELAY) {
            revert InvalidDelay(initialAdminDelay);
        }
        _grantRole(REGISTRAR_ROLE, msg.sender);
        _grantRole(REVOKER_ROLE, msg.sender);
        _grantRole(PAUSER_ROLE, msg.sender);
    }

    function _changeDefaultAdminDelay(uint48 newDelay) internal override {
        if (newDelay < MIN_ADMIN_DELAY) {
            revert InvalidDelay(newDelay);
        }
        super._changeDefaultAdminDelay(newDelay);
    }

    function canonicalizeParcelId(string calldata parcelId) public pure returns (string memory) {
        bytes memory bStr = bytes(parcelId);
        if (bStr.length == 0) revert InvalidParcelId();
        if (bStr.length > MAX_PARCEL_ID_LENGTH) revert ParcelIdTooLong(bStr.length);

        if (bStr[0] == 0x20 || bStr[bStr.length - 1] == 0x20) {
            revert InvalidParcelIdWhitespace();
        }

        bytes memory bUpper = new bytes(bStr.length);
        for (uint256 i = 0; i < bStr.length; i++) {
            uint8 b = uint8(bStr[i]);
            if (b >= 97 && b <= 122) {
                bUpper[i] = bytes1(b - 32);
            } else {
                bUpper[i] = bytes1(b);
            }
        }
        return string(bUpper);
    }

    function registerRecord(
        string calldata parcelId,
        bytes32 documentHash,
        string calldata metadataURI
    ) external onlyRole(REGISTRAR_ROLE) whenNotPaused {
        _registerInternal(parcelId, documentHash, metadataURI);
    }

    function updateRecord(
        string calldata parcelId,
        bytes32 documentHash,
        string calldata metadataURI
    ) external onlyRole(REGISTRAR_ROLE) whenNotPaused {
        _updateInternal(parcelId, documentHash, metadataURI);
    }

    function batchRegisterRecords(
        string[] calldata parcelIds,
        bytes32[] calldata documentHashes,
        string[] calldata metadataURIs
    ) external onlyRole(REGISTRAR_ROLE) whenNotPaused {
        uint256 len = parcelIds.length;
        if (len == 0) revert EmptyBatch();
        if (len != documentHashes.length || len != metadataURIs.length) revert ArrayLengthMismatch();
        if (len > MAX_BATCH_SIZE) revert BatchSizeExceeded(len, MAX_BATCH_SIZE);

        for (uint256 i = 0; i < len; i++) {
            _registerInternal(parcelIds[i], documentHashes[i], metadataURIs[i]);
        }
    }

    function revokeRecordVersion(
        string calldata parcelId,
        uint256 version,
        RevocationReason reasonCode,
        string calldata revocationReference
    ) external onlyRole(REVOKER_ROLE) whenNotPaused {
        if (bytes(revocationReference).length > MAX_REFERENCE_LENGTH) revert ReferenceTooLong(bytes(revocationReference).length);
        if (reasonCode != RevocationReason.Unspecified && bytes(revocationReference).length == 0) {
            revert EmptyRevocationReference();
        }

        string memory cParcelId = canonicalizeParcelId(parcelId);
        ParcelRecord storage parcel = _parcels[cParcelId];
        if (!parcel.exists) revert ParcelDoesNotExist(cParcelId);
        if (version == 0 || version > parcel.activeVersion) revert VersionDoesNotExist(version);

        RecordVersion storage recVersion = _parcelVersions[cParcelId][version];
        if (recVersion.isRevoked) revert VersionAlreadyRevoked(version);

        recVersion.isRevoked = true;
        recVersion.reasonCode = reasonCode;
        recVersion.revocationReference = revocationReference;

        emit RecordVersionRevoked(cParcelId, version, reasonCode, revocationReference, msg.sender);
    }

    function verifyRecord(
        string calldata parcelId,
        bytes32 documentHash
    ) external view returns (bool isValid, uint256 activeVersion, bool isRevoked) {
        string memory cParcelId = canonicalizeParcelId(parcelId);
        ParcelRecord storage parcel = _parcels[cParcelId];
        if (!parcel.exists) return (false, 0, false);

        activeVersion = parcel.activeVersion;
        RecordVersion storage recVersion = _parcelVersions[cParcelId][activeVersion];

        isValid = (recVersion.documentHash == documentHash && !recVersion.isRevoked);
        isRevoked = recVersion.isRevoked;
    }

    function getCurrentRecord(
        string calldata parcelId
    ) external view returns (RecordVersion memory) {
        string memory cParcelId = canonicalizeParcelId(parcelId);
        ParcelRecord storage parcel = _parcels[cParcelId];
        if (!parcel.exists) revert ParcelDoesNotExist(cParcelId);

        return _parcelVersions[cParcelId][parcel.activeVersion];
    }

    function getVersionCount(
        string calldata parcelId
    ) external view returns (uint256) {
        string memory cParcelId = canonicalizeParcelId(parcelId);
        ParcelRecord storage parcel = _parcels[cParcelId];
        if (!parcel.exists) revert ParcelDoesNotExist(cParcelId);

        return parcel.activeVersion;
    }

    function getRecordVersion(
        string calldata parcelId,
        uint256 version
    ) external view returns (RecordVersion memory) {
        string memory cParcelId = canonicalizeParcelId(parcelId);
        if (!_parcels[cParcelId].exists) revert ParcelDoesNotExist(cParcelId);
        if (version == 0 || version > _parcels[cParcelId].activeVersion) revert VersionDoesNotExist(version);

        return _parcelVersions[cParcelId][version];
    }

    function isDocumentHashUsed(bytes32 documentHash) external view returns (bool) {
        return _usedDocumentHashes[documentHash];
    }

    function pause() external onlyRole(PAUSER_ROLE) {
        _pause();
    }

    function unpause() external onlyRole(PAUSER_ROLE) {
        _unpause();
    }

    function _registerInternal(
        string calldata parcelId,
        bytes32 documentHash,
        string calldata metadataURI
    ) internal {
        if (documentHash == bytes32(0)) revert InvalidDocumentHash();
        if (_usedDocumentHashes[documentHash]) revert DocumentHashAlreadyUsed(documentHash);
        if (bytes(metadataURI).length > MAX_METADATA_LENGTH) revert MetadataURITooLong(bytes(metadataURI).length);

        string memory cParcelId = canonicalizeParcelId(parcelId);
        if (_parcels[cParcelId].exists) revert ParcelAlreadyExists(cParcelId);

        _parcels[cParcelId] = ParcelRecord({
            canonicalParcelId: cParcelId,
            exists: true,
            activeVersion: 1
        });

        _parcelVersions[cParcelId][1] = RecordVersion({
            version: 1,
            documentHash: documentHash,
            metadataURI: metadataURI,
            registeredBy: msg.sender,
            timestamp: uint64(block.timestamp),
            isRevoked: false,
            reasonCode: RevocationReason.Unspecified,
            revocationReference: ""
        });

        _usedDocumentHashes[documentHash] = true;

        emit RecordRegistered(cParcelId, 1, documentHash, metadataURI, msg.sender);
    }

    function _updateInternal(
        string calldata parcelId,
        bytes32 documentHash,
        string calldata metadataURI
    ) internal {
        if (documentHash == bytes32(0)) revert InvalidDocumentHash();
        if (_usedDocumentHashes[documentHash]) revert DocumentHashAlreadyUsed(documentHash);
        if (bytes(metadataURI).length > MAX_METADATA_LENGTH) revert MetadataURITooLong(bytes(metadataURI).length);

        string memory cParcelId = canonicalizeParcelId(parcelId);
        ParcelRecord storage parcel = _parcels[cParcelId];
        if (!parcel.exists) revert ParcelDoesNotExist(cParcelId);

        uint256 newVersion = parcel.activeVersion + 1;
        parcel.activeVersion = newVersion;

        _parcelVersions[cParcelId][newVersion] = RecordVersion({
            version: newVersion,
            documentHash: documentHash,
            metadataURI: metadataURI,
            registeredBy: msg.sender,
            timestamp: uint64(block.timestamp),
            isRevoked: false,
            reasonCode: RevocationReason.Unspecified,
            revocationReference: ""
        });

        _usedDocumentHashes[documentHash] = true;

        emit RecordUpdated(cParcelId, newVersion, documentHash, metadataURI, msg.sender);
    }
}
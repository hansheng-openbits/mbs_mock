// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title ITransferValidator
 * @notice Interface for transfer validation logic (KYC, compliance checks)
 * @dev Implements pluggable compliance validation for security tokens
 */
interface ITransferValidator {
    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    event TransferRuleUpdated(bytes32 indexed dealId, string ruleType, bool enabled);
    event InvestorWhitelisted(bytes32 indexed dealId, address indexed investor);
    event InvestorBlacklisted(bytes32 indexed dealId, address indexed investor);

    // ═══════════════════════════════════════════════════════════════════════
    // VALIDATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Validate a transfer
     * @param dealId Unique identifier for the deal
     * @param from Sender address
     * @param to Recipient address
     * @param value Amount to transfer
     * @return valid true if transfer is allowed
     * @return code Status code (0x51 = valid, others = error codes)
     * @return message Human-readable message
     */
    function validateTransfer(
        bytes32 dealId,
        address from,
        address to,
        uint256 value
    ) external view returns (bool valid, bytes1 code, string memory message);

    /**
     * @notice Check if an investor is KYC verified
     * @param investor Address to check
     * @return true if KYC verified
     */
    function isKYCVerified(address investor) external view returns (bool);

    /**
     * @notice Check if an investor is accredited
     * @param investor Address to check
     * @return true if accredited
     */
    function isAccredited(address investor) external view returns (bool);

    /**
     * @notice Check if jurisdiction is allowed
     * @param jurisdiction Two-letter country code (e.g., "US", "GB")
     * @return true if jurisdiction is allowed
     */
    function isJurisdictionAllowed(bytes2 jurisdiction) external view returns (bool);

    // ═══════════════════════════════════════════════════════════════════════
    // MANAGEMENT (Admin only)
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Set KYC status for an investor
     * @param investor Address
     * @param verified KYC status
     */
    function setKYCStatus(address investor, bool verified) external;

    /**
     * @notice Set accreditation status for an investor
     * @param investor Address
     * @param accredited Accreditation status
     */
    function setAccreditationStatus(address investor, bool accredited) external;

    /**
     * @notice Add allowed jurisdiction
     * @param jurisdiction Two-letter country code
     */
    function addJurisdiction(bytes2 jurisdiction) external;

    /**
     * @notice Remove allowed jurisdiction
     * @param jurisdiction Two-letter country code
     */
    function removeJurisdiction(bytes2 jurisdiction) external;
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IERC1400 Security Token Standard
 * @notice Interface for security tokens with partitions and transfer restrictions
 * @dev Implements ERC-1400 standard for regulated securities
 * 
 * Key Features:
 * - Partitioned balances for lock-up tracking
 * - Transfer restrictions (KYC, accreditation, jurisdiction)
 * - Document management
 * - Controller operations for legal compliance
 */
interface IERC1400 {
    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Document attached to the token
    event Document(bytes32 indexed name, string uri, bytes32 documentHash);

    /// @notice Tokens issued
    event Issued(address indexed operator, address indexed to, uint256 amount, bytes data);

    /// @notice Tokens redeemed
    event Redeemed(address indexed operator, address indexed from, uint256 amount, bytes data);

    /// @notice Controller transfer
    event ControllerTransfer(
        address indexed controller,
        address indexed from,
        address indexed to,
        uint256 amount,
        bytes data,
        bytes operatorData
    );

    /// @notice Controller redemption
    event ControllerRedemption(
        address indexed controller,
        address indexed tokenHolder,
        uint256 amount,
        bytes data,
        bytes operatorData
    );

    // ═══════════════════════════════════════════════════════════════════════
    // TRANSFER VALIDATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Check if a transfer can be executed
     * @param from Token holder
     * @param to Token recipient
     * @param value Amount to transfer
     * @return ESC (Ethereum Status Code) - 0x51 = valid, others = error codes
     * @return reason Human-readable reason
     */
    function canTransfer(
        address from,
        address to,
        uint256 value
    ) external view returns (bytes1 ESC, string memory reason);

    // ═══════════════════════════════════════════════════════════════════════
    // DOCUMENT MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Set or update a document
     * @param name Document identifier (e.g., "PROSPECTUS", "TERM_SHEET")
     * @param uri Document URI (IPFS hash or URL)
     * @param documentHash Hash of the document for integrity verification
     */
    function setDocument(bytes32 name, string calldata uri, bytes32 documentHash) external;

    /**
     * @notice Get document details
     * @param name Document identifier
     * @return uri Document URI
     * @return documentHash Document hash
     * @return timestamp Last updated timestamp
     */
    function getDocument(bytes32 name)
        external
        view
        returns (string memory uri, bytes32 documentHash, uint256 timestamp);

    /**
     * @notice Get all document names
     * @return Array of document names
     */
    function getAllDocuments() external view returns (bytes32[] memory);

    // ═══════════════════════════════════════════════════════════════════════
    // ISSUANCE & REDEMPTION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Issue new tokens
     * @param tokenHolder Address to issue tokens to
     * @param value Amount to issue
     * @param data Additional data
     */
    function issue(address tokenHolder, uint256 value, bytes calldata data) external;

    /**
     * @notice Redeem tokens
     * @param value Amount to redeem
     * @param data Additional data
     */
    function redeem(uint256 value, bytes calldata data) external;

    /**
     * @notice Redeem tokens from a holder (controller operation)
     * @param tokenHolder Address to redeem from
     * @param value Amount to redeem
     * @param data Additional data
     */
    function redeemFrom(address tokenHolder, uint256 value, bytes calldata data) external;

    // ═══════════════════════════════════════════════════════════════════════
    // CONTROLLER OPERATIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Force a transfer (e.g., court order, regulatory requirement)
     * @param from Token holder
     * @param to Recipient
     * @param value Amount
     * @param data Additional data
     * @param operatorData Operator data (reason for force transfer)
     */
    function controllerTransfer(
        address from,
        address to,
        uint256 value,
        bytes calldata data,
        bytes calldata operatorData
    ) external;

    /**
     * @notice Force a redemption (e.g., regulatory seizure)
     * @param tokenHolder Address to redeem from
     * @param value Amount to redeem
     * @param data Additional data
     * @param operatorData Operator data (reason for redemption)
     */
    function controllerRedeem(
        address tokenHolder,
        uint256 value,
        bytes calldata data,
        bytes calldata operatorData
    ) external;

    /**
     * @notice Check if controller operations are enabled
     * @return true if controller operations are enabled
     */
    function isControllable() external view returns (bool);
}

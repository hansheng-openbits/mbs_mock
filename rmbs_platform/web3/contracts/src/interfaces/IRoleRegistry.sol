// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IRoleRegistry
 * @notice Interface for the RoleRegistry contract
 * @dev Manages platform-wide and deal-specific roles
 */
interface IRoleRegistry {
    // ═══════════════════════════════════════════════════════════════════════
    // PLATFORM ROLES
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Grant a platform-wide role to an account
     * @param role Role identifier
     * @param account Address to grant the role to
     * @param expiresAt Unix timestamp when the role expires (0 for no expiry)
     */
    function grantPlatformRole(bytes32 role, address account, uint64 expiresAt) external;

    /**
     * @notice Revoke a platform-wide role from an account
     * @param role Role identifier
     * @param account Address to revoke the role from
     */
    function revokePlatformRole(bytes32 role, address account) external;

    /**
     * @notice Check if an account has a platform-wide role
     * @param role Role identifier
     * @param account Address to check
     * @return true if the account has the role and it hasn't expired
     */
    function hasPlatformRole(bytes32 role, address account) external view returns (bool);

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL-SPECIFIC ROLES
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Grant a deal-specific role to an account
     * @param dealId Deal identifier
     * @param role Role identifier
     * @param account Address to grant the role to
     * @param expiresAt Unix timestamp when the role expires (0 for no expiry)
     */
    function grantDealRole(bytes32 dealId, bytes32 role, address account, uint64 expiresAt) external;

    /**
     * @notice Revoke a deal-specific role from an account
     * @param dealId Deal identifier
     * @param role Role identifier
     * @param account Address to revoke the role from
     */
    function revokeDealRole(bytes32 dealId, bytes32 role, address account) external;

    /**
     * @notice Check if an account has a deal-specific role
     * @param dealId Deal identifier
     * @param role Role identifier
     * @param account Address to check
     * @return true if the account has the role and it hasn't expired
     */
    function hasDealRole(bytes32 dealId, bytes32 role, address account) external view returns (bool);

    // ═══════════════════════════════════════════════════════════════════════
    // BATCH OPERATIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Grant a platform-wide role to multiple accounts
     * @param role Role identifier
     * @param accounts Array of addresses to grant the role to
     * @param expiresAt Unix timestamp when the role expires
     */
    function batchGrantPlatformRole(bytes32 role, address[] calldata accounts, uint64 expiresAt) external;

    /**
     * @notice Grant a deal-specific role to multiple accounts
     * @param dealId Deal identifier
     * @param role Role identifier
     * @param accounts Array of addresses to grant the role to
     * @param expiresAt Unix timestamp when the role expires
     */
    function batchGrantDealRole(bytes32 dealId, bytes32 role, address[] calldata accounts, uint64 expiresAt) external;
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title IServicerOracle
 * @notice Interface for the ServicerOracle contract
 * @dev Manages submission and verification of cashflow data from servicers
 */
interface IServicerOracle {
    // ═══════════════════════════════════════════════════════════════════════
    // STRUCTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Cashflow data submitted by servicers
    struct CashflowData {
        uint256 totalPrincipal; // Total principal collected
        uint256 totalInterest; // Total interest collected
        uint256 totalPrepayments; // Total prepayments
        uint256 totalDefaults; // Total defaults
        uint256 numLoansActive; // Number of active loans
        uint256 numLoansDefaulted; // Number of defaulted loans
        uint256 avgLTV; // Average LTV in basis points (e.g., 7500 for 75%)
        uint256 avgFICO; // Average FICO score
        bytes32 dataHash; // Hash of raw data for verification
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SERVICER VERIFICATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Add a verified servicer for a specific deal
     * @param dealId Deal identifier
     * @param servicer Address of the servicer
     */
    function addVerifiedServicer(bytes32 dealId, address servicer) external;

    /**
     * @notice Remove a verified servicer for a specific deal
     * @param dealId Deal identifier
     * @param servicer Address of the servicer
     */
    function removeVerifiedServicer(bytes32 dealId, address servicer) external;

    /**
     * @notice Check if a servicer is verified for a specific deal
     * @param dealId Deal identifier
     * @param servicer Address of the servicer
     * @return true if the servicer is verified
     */
    function isVerifiedServicer(bytes32 dealId, address servicer) external view returns (bool);

    // ═══════════════════════════════════════════════════════════════════════
    // CASHFLOW DATA SUBMISSION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Submit cashflow data for a specific deal and period
     * @param dealId Deal identifier
     * @param period Payment period
     * @param data Cashflow data
     */
    function submitCashflow(bytes32 dealId, uint256 period, CashflowData calldata data) external;

    /**
     * @notice Batch submit cashflow data for multiple periods
     * @param dealId Deal identifier
     * @param periods Array of payment periods
     * @param dataArray Array of cashflow data
     */
    function batchSubmitCashflows(
        bytes32 dealId,
        uint256[] calldata periods,
        CashflowData[] calldata dataArray
    ) external;

    /**
     * @notice Get cashflow data for a specific deal and period
     * @param dealId Deal identifier
     * @param period Payment period
     * @return totalPrincipal Total principal collected
     * @return totalInterest Total interest collected
     * @return totalPrepayments Total prepayments
     * @return totalDefaults Total defaults
     * @return numLoansActive Number of active loans
     * @return numLoansDefaulted Number of defaulted loans
     * @return avgLTV Average LTV
     * @return avgFICO Average FICO score
     * @return dataHash Hash of raw data
     * @return submitter Address of submitter
     * @return timestamp Timestamp of submission
     * @return verified Whether data is verified
     */
    function getCashflowData(bytes32 dealId, uint256 period)
        external
        view
        returns (
            uint256 totalPrincipal,
            uint256 totalInterest,
            uint256 totalPrepayments,
            uint256 totalDefaults,
            uint256 numLoansActive,
            uint256 numLoansDefaulted,
            uint256 avgLTV,
            uint256 avgFICO,
            bytes32 dataHash,
            address submitter,
            uint256 timestamp,
            bool verified
        );

    /**
     * @notice Get the latest period with cashflow data
     * @param dealId Deal identifier
     * @return Latest period number
     */
    function getLatestPeriod(bytes32 dealId) external view returns (uint256);

    /**
     * @notice Check if cashflow data exists for a specific deal and period
     * @param dealId Deal identifier
     * @param period Payment period
     * @return true if data exists
     */
    function hasCashflowData(bytes32 dealId, uint256 period) external view returns (bool);
}

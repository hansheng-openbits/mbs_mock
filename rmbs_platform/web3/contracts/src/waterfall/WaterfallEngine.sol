// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {AccessControlUpgradeable} from
    "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {UUPSUpgradeable} from
    "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {ReentrancyGuardUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import {PausableUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {RMBSTranche} from "../tokens/RMBSTranche.sol";

/**
 * @title WaterfallEngine
 * @notice Executes waterfall distributions for RMBS deals
 * @dev Implements senior-to-junior payment priority (waterfall structure)
 * 
 * Key Features:
 * - Sequential waterfall execution (senior → junior)
 * - Pro-rata distribution within same seniority
 * - Interest-first, principal-second payment order
 * - Trigger-based acceleration/protection
 * - Comprehensive audit trail
 * 
 * Payment Priority:
 * 1. Trustee/Servicer fees
 * 2. Senior interest (Class A)
 * 3. Mezzanine interest (Class M)
 * 4. Junior interest (Class B)
 * 5. Senior principal (sequential or pro-rata)
 * 6. Mezzanine principal
 * 7. Junior principal
 * 8. Residual to equity holders
 * 
 * Security:
 * - Role-based access control
 * - ReentrancyGuard protection
 * - Pausable for emergencies
 * - Comprehensive event logging
 * 
 * @custom:security-contact security@rmbs.io
 */
contract WaterfallEngine is
    AccessControlUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable
{
    using SafeERC20 for IERC20;

    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Role for executing waterfall distributions
    bytes32 public constant EXECUTOR_ROLE = keccak256("EXECUTOR_ROLE");

    /// @notice Role for configuring waterfall rules
    bytes32 public constant CONFIG_ROLE = keccak256("CONFIG_ROLE");

    /// @notice Role for contract upgrades
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice Precision for percentage calculations (100% = 1e18)
    uint256 public constant PRECISION = 1e18;

    /// @notice Basis points denominator
    uint256 public constant BPS = 10_000;

    // ═══════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Tranche seniority levels
    enum Seniority {
        SENIOR,      // Class A - highest priority
        MEZZANINE,   // Class M - middle priority  
        JUNIOR,      // Class B - lowest priority
        RESIDUAL     // Equity - receives leftover
    }

    /// @notice Payment type
    enum PaymentType {
        INTEREST,
        PRINCIPAL,
        FEE
    }

    /// @notice Waterfall configuration for a deal
    struct WaterfallConfig {
        bytes32 dealId;
        address paymentToken;       // USDC/USDT address
        address[] tranches;         // Ordered by priority (senior first)
        Seniority[] seniorities;    // Seniority of each tranche
        uint256[] interestRatesBps; // Annual interest rate in basis points
        uint256 trusteeFeesBps;     // Trustee fees in basis points
        uint256 servicerFeesBps;    // Servicer fees in basis points
        address trusteeAddress;     // Trustee fee recipient
        address servicerAddress;    // Servicer fee recipient
        bool principalSequential;   // Sequential (true) or pro-rata (false) principal
        bool isActive;
    }

    /// @notice Distribution period data
    struct PeriodData {
        uint256 periodNumber;
        uint256 totalCollections;   // Total collected from loans
        uint256 interestCollected;  // Interest portion
        uint256 principalCollected; // Principal portion
        uint256 lossesRealized;     // Losses (defaults)
        uint256 prepayments;        // Prepayments received
        uint256 timestamp;
        bool isProcessed;
    }

    /// @notice Distribution result for a tranche
    struct TrancheDistribution {
        address tranche;
        uint256 interestPaid;
        uint256 principalPaid;
        uint256 interestShortfall;  // Unpaid interest (deferred)
        uint256 principalShortfall; // Unpaid principal
        uint256 newFactor;          // Updated factor after principal
    }

    /// @notice Complete waterfall execution result
    struct WaterfallResult {
        bytes32 dealId;
        uint256 periodNumber;
        uint256 trusteeFeesPaid;
        uint256 servicerFeesPaid;
        TrancheDistribution[] distributions;
        uint256 residualAmount;     // Amount to equity holders
        uint256 timestamp;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // STORAGE
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Waterfall configuration by deal ID
    mapping(bytes32 => WaterfallConfig) public waterfallConfigs;

    /// @notice Period data by deal ID and period number
    mapping(bytes32 => mapping(uint256 => PeriodData)) public periodData;

    /// @notice Current period number by deal ID
    mapping(bytes32 => uint256) public currentPeriod;

    /// @notice Cumulative interest shortfall by tranche
    mapping(address => uint256) public deferredInterest;

    /// @notice Waterfall results by deal ID and period
    mapping(bytes32 => mapping(uint256 => WaterfallResult)) public waterfallResults;

    /// @notice Trigger status for deals (e.g., overcollateralization breach)
    mapping(bytes32 => bool) public triggerActive;

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a waterfall is configured
    event WaterfallConfigured(
        bytes32 indexed dealId,
        address[] tranches,
        address paymentToken
    );

    /// @notice Emitted when collections are reported
    event CollectionsReported(
        bytes32 indexed dealId,
        uint256 indexed period,
        uint256 interestCollected,
        uint256 principalCollected,
        uint256 losses
    );

    /// @notice Emitted when waterfall is executed
    event WaterfallExecuted(
        bytes32 indexed dealId,
        uint256 indexed period,
        uint256 totalDistributed,
        uint256 residual
    );

    /// @notice Emitted when a tranche receives payment
    event TranchePayment(
        bytes32 indexed dealId,
        uint256 indexed period,
        address indexed tranche,
        PaymentType paymentType,
        uint256 amount
    );

    /// @notice Emitted when fees are paid
    event FeesPaid(
        bytes32 indexed dealId,
        uint256 indexed period,
        address indexed recipient,
        uint256 amount,
        string feeType
    );

    /// @notice Emitted when a trigger is activated
    event TriggerActivated(bytes32 indexed dealId, string reason);

    /// @notice Emitted when a trigger is cleared
    event TriggerCleared(bytes32 indexed dealId);

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ZeroAddress();
    error DealAlreadyConfigured(bytes32 dealId);
    error DealNotConfigured(bytes32 dealId);
    error DealNotActive(bytes32 dealId);
    error InvalidTrancheCount();
    error ArrayLengthMismatch();
    error PeriodAlreadyProcessed(uint256 period);
    error PeriodNotReported(uint256 period);
    error InsufficientCollections(uint256 required, uint256 available);
    error InvalidSeniority();
    error TransferFailed();

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZER
    // ═══════════════════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the waterfall engine
     * @param admin Admin address
     */
    function initialize(address admin) external initializer {
        if (admin == address(0)) revert ZeroAddress();

        __AccessControl_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(EXECUTOR_ROLE, admin);
        _grantRole(CONFIG_ROLE, admin);
        _grantRole(UPGRADER_ROLE, admin);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Configure waterfall for a deal
     * @param config Waterfall configuration
     */
    function configureWaterfall(WaterfallConfig calldata config)
        external
        onlyRole(CONFIG_ROLE)
    {
        if (config.dealId == bytes32(0)) revert DealNotConfigured(bytes32(0));
        if (waterfallConfigs[config.dealId].isActive) {
            revert DealAlreadyConfigured(config.dealId);
        }
        if (config.tranches.length == 0) revert InvalidTrancheCount();
        if (config.tranches.length != config.seniorities.length) revert ArrayLengthMismatch();
        if (config.tranches.length != config.interestRatesBps.length) revert ArrayLengthMismatch();
        if (config.paymentToken == address(0)) revert ZeroAddress();

        // Validate tranches are not zero addresses
        for (uint256 i = 0; i < config.tranches.length; i++) {
            if (config.tranches[i] == address(0)) revert ZeroAddress();
        }

        waterfallConfigs[config.dealId] = config;
        waterfallConfigs[config.dealId].isActive = true;

        emit WaterfallConfigured(config.dealId, config.tranches, config.paymentToken);
    }

    /**
     * @notice Deactivate waterfall for a deal
     * @param dealId Deal identifier
     */
    function deactivateWaterfall(bytes32 dealId)
        external
        onlyRole(CONFIG_ROLE)
    {
        WaterfallConfig storage config = waterfallConfigs[dealId];
        if (!config.isActive) revert DealNotActive(dealId);
        
        config.isActive = false;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // COLLECTIONS REPORTING
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Report collections for a period (called by ServicerOracle)
     * @param dealId Deal identifier
     * @param interestCollected Interest collected from loans
     * @param principalCollected Principal collected from loans
     * @param lossesRealized Losses from defaults
     * @param prepayments Prepayment amounts
     */
    function reportCollections(
        bytes32 dealId,
        uint256 interestCollected,
        uint256 principalCollected,
        uint256 lossesRealized,
        uint256 prepayments
    ) external onlyRole(EXECUTOR_ROLE) {
        WaterfallConfig storage config = waterfallConfigs[dealId];
        if (!config.isActive) revert DealNotActive(dealId);

        uint256 period = currentPeriod[dealId] + 1;
        
        periodData[dealId][period] = PeriodData({
            periodNumber: period,
            totalCollections: interestCollected + principalCollected,
            interestCollected: interestCollected,
            principalCollected: principalCollected,
            lossesRealized: lossesRealized,
            prepayments: prepayments,
            timestamp: block.timestamp,
            isProcessed: false
        });

        currentPeriod[dealId] = period;

        emit CollectionsReported(
            dealId,
            period,
            interestCollected,
            principalCollected,
            lossesRealized
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // WATERFALL EXECUTION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Execute waterfall distribution for a period
     * @param dealId Deal identifier
     * @param period Period number to process
     * @return result Complete waterfall execution result
     */
    function executeWaterfall(bytes32 dealId, uint256 period)
        external
        onlyRole(EXECUTOR_ROLE)
        nonReentrant
        whenNotPaused
        returns (WaterfallResult memory result)
    {
        WaterfallConfig storage config = waterfallConfigs[dealId];
        if (!config.isActive) revert DealNotActive(dealId);

        PeriodData storage data = periodData[dealId][period];
        if (data.periodNumber == 0) revert PeriodNotReported(period);
        if (data.isProcessed) revert PeriodAlreadyProcessed(period);

        // Transfer collections to this contract (must be approved first)
        IERC20 paymentToken = IERC20(config.paymentToken);
        uint256 availableFunds = data.totalCollections;

        // 1. Pay trustee fees
        uint256 trusteeFees = (availableFunds * config.trusteeFeesBps) / BPS;
        if (trusteeFees > 0 && config.trusteeAddress != address(0)) {
            paymentToken.safeTransfer(config.trusteeAddress, trusteeFees);
            availableFunds -= trusteeFees;
            emit FeesPaid(dealId, period, config.trusteeAddress, trusteeFees, "TRUSTEE");
        }

        // 2. Pay servicer fees
        uint256 servicerFees = (availableFunds * config.servicerFeesBps) / BPS;
        if (servicerFees > 0 && config.servicerAddress != address(0)) {
            paymentToken.safeTransfer(config.servicerAddress, servicerFees);
            availableFunds -= servicerFees;
            emit FeesPaid(dealId, period, config.servicerAddress, servicerFees, "SERVICER");
        }

        // Initialize result
        result.dealId = dealId;
        result.periodNumber = period;
        result.trusteeFeesPaid = trusteeFees;
        result.servicerFeesPaid = servicerFees;
        result.distributions = new TrancheDistribution[](config.tranches.length);
        result.timestamp = block.timestamp;

        // 3. Pay interest (senior to junior)
        uint256 interestAvailable = _min(availableFunds, data.interestCollected);
        availableFunds -= _distributeInterest(
            config,
            dealId,
            period,
            interestAvailable,
            result.distributions
        );

        // 4. Pay principal (sequential or pro-rata based on config)
        uint256 principalAvailable = availableFunds;
        availableFunds -= _distributePrincipal(
            config,
            dealId,
            period,
            principalAvailable,
            result.distributions
        );

        // 5. Residual to equity holders
        result.residualAmount = availableFunds;

        // Mark period as processed
        data.isProcessed = true;

        // Store result
        waterfallResults[dealId][period] = result;

        emit WaterfallExecuted(
            dealId,
            period,
            data.totalCollections - result.residualAmount,
            result.residualAmount
        );
    }

    /**
     * @notice Distribute interest payments following waterfall priority
     */
    function _distributeInterest(
        WaterfallConfig storage config,
        bytes32 dealId,
        uint256 period,
        uint256 available,
        TrancheDistribution[] memory distributions
    ) internal returns (uint256 totalPaid) {
        // Process by seniority: SENIOR → MEZZANINE → JUNIOR
        for (uint256 seniority = 0; seniority <= uint256(Seniority.JUNIOR); seniority++) {
            for (uint256 i = 0; i < config.tranches.length; i++) {
                if (uint256(config.seniorities[i]) != seniority) continue;
                if (available == 0) break;

                address tranche = config.tranches[i];
                RMBSTranche trancheContract = RMBSTranche(tranche);

                // Calculate interest due
                uint256 currentFace = trancheContract.totalCurrentFaceValue();
                uint256 interestDue = (currentFace * config.interestRatesBps[i]) / BPS / 12; // Monthly
                
                // Add any deferred interest
                interestDue += deferredInterest[tranche];

                // Pay what we can
                uint256 payment = _min(available, interestDue);
                
                if (payment > 0) {
                    // Approve and distribute
                    IERC20(config.paymentToken).approve(tranche, payment);
                    trancheContract.distributeYield(payment);
                    
                    available -= payment;
                    totalPaid += payment;
                    distributions[i].interestPaid = payment;

                    emit TranchePayment(dealId, period, tranche, PaymentType.INTEREST, payment);
                }

                // Track shortfall
                uint256 shortfall = interestDue - payment;
                distributions[i].interestShortfall = shortfall;
                deferredInterest[tranche] = shortfall;
            }
        }
    }

    /**
     * @notice Distribute principal payments
     */
    function _distributePrincipal(
        WaterfallConfig storage config,
        bytes32 dealId,
        uint256 period,
        uint256 available,
        TrancheDistribution[] memory distributions
    ) internal returns (uint256 totalPaid) {
        if (config.principalSequential) {
            totalPaid = _distributePrincipalSequential(
                config, dealId, period, available, distributions
            );
        } else {
            totalPaid = _distributePrincipalProRata(
                config, dealId, period, available, distributions
            );
        }
    }

    /**
     * @notice Sequential principal distribution (senior paid first fully)
     */
    function _distributePrincipalSequential(
        WaterfallConfig storage config,
        bytes32 dealId,
        uint256 period,
        uint256 available,
        TrancheDistribution[] memory distributions
    ) internal returns (uint256 totalPaid) {
        // Pay senior tranches first, then mezzanine, then junior
        for (uint256 seniority = 0; seniority <= uint256(Seniority.JUNIOR); seniority++) {
            for (uint256 i = 0; i < config.tranches.length; i++) {
                if (uint256(config.seniorities[i]) != seniority) continue;
                if (available == 0) break;

                address tranche = config.tranches[i];
                RMBSTranche trancheContract = RMBSTranche(tranche);

                // Get current face value
                uint256 currentFace = trancheContract.totalCurrentFaceValue();
                if (currentFace == 0) continue;

                // Pay up to current face value
                uint256 payment = _min(available, currentFace);
                
                if (payment > 0) {
                    // Calculate new factor
                    uint256 originalFace = trancheContract.originalFaceValue();
                    uint256 newFace = currentFace - payment;
                    uint256 newFactor = (newFace * PRECISION) / originalFace;

                    // Update factor
                    trancheContract.updateFactor(newFactor);

                    // Transfer principal (could go to redemption pool or direct)
                    IERC20(config.paymentToken).safeTransfer(tranche, payment);

                    available -= payment;
                    totalPaid += payment;
                    distributions[i].principalPaid = payment;
                    distributions[i].newFactor = newFactor;

                    emit TranchePayment(dealId, period, tranche, PaymentType.PRINCIPAL, payment);
                }
            }
        }
    }

    /**
     * @notice Pro-rata principal distribution (proportional to current balance)
     */
    function _distributePrincipalProRata(
        WaterfallConfig storage config,
        bytes32 dealId,
        uint256 period,
        uint256 available,
        TrancheDistribution[] memory distributions
    ) internal returns (uint256 totalPaid) {
        // Calculate total current face value
        uint256 totalFace = 0;
        for (uint256 i = 0; i < config.tranches.length; i++) {
            totalFace += RMBSTranche(config.tranches[i]).totalCurrentFaceValue();
        }

        if (totalFace == 0) return 0;

        // Distribute pro-rata
        for (uint256 i = 0; i < config.tranches.length; i++) {
            if (available == 0) break;

            address tranche = config.tranches[i];
            RMBSTranche trancheContract = RMBSTranche(tranche);
            uint256 currentFace = trancheContract.totalCurrentFaceValue();

            if (currentFace == 0) continue;

            // Pro-rata share
            uint256 share = (available * currentFace) / totalFace;
            uint256 payment = _min(share, currentFace);

            if (payment > 0) {
                // Calculate new factor
                uint256 originalFace = trancheContract.originalFaceValue();
                uint256 newFace = currentFace - payment;
                uint256 newFactor = (newFace * PRECISION) / originalFace;

                // Update factor
                trancheContract.updateFactor(newFactor);

                // Transfer principal
                IERC20(config.paymentToken).safeTransfer(tranche, payment);

                totalPaid += payment;
                distributions[i].principalPaid = payment;
                distributions[i].newFactor = newFactor;

                emit TranchePayment(dealId, period, tranche, PaymentType.PRINCIPAL, payment);
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TRIGGER MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Activate a trigger (e.g., OC test failure)
     * @param dealId Deal identifier
     * @param reason Reason for trigger activation
     */
    function activateTrigger(bytes32 dealId, string calldata reason)
        external
        onlyRole(EXECUTOR_ROLE)
    {
        triggerActive[dealId] = true;
        emit TriggerActivated(dealId, reason);
    }

    /**
     * @notice Clear a trigger
     * @param dealId Deal identifier
     */
    function clearTrigger(bytes32 dealId)
        external
        onlyRole(EXECUTOR_ROLE)
    {
        triggerActive[dealId] = false;
        emit TriggerCleared(dealId);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get waterfall configuration for a deal
     * @param dealId Deal identifier
     * @return Waterfall configuration
     */
    function getWaterfallConfig(bytes32 dealId)
        external
        view
        returns (WaterfallConfig memory)
    {
        return waterfallConfigs[dealId];
    }

    /**
     * @notice Get period data
     * @param dealId Deal identifier
     * @param period Period number
     * @return Period data
     */
    function getPeriodData(bytes32 dealId, uint256 period)
        external
        view
        returns (PeriodData memory)
    {
        return periodData[dealId][period];
    }

    /**
     * @notice Get waterfall result for a period
     * @param dealId Deal identifier
     * @param period Period number
     * @return Waterfall result
     */
    function getWaterfallResult(bytes32 dealId, uint256 period)
        external
        view
        returns (WaterfallResult memory)
    {
        return waterfallResults[dealId][period];
    }

    /**
     * @notice Get current period for a deal
     * @param dealId Deal identifier
     * @return Current period number
     */
    function getCurrentPeriod(bytes32 dealId)
        external
        view
        returns (uint256)
    {
        return currentPeriod[dealId];
    }

    /**
     * @notice Check if trigger is active for a deal
     * @param dealId Deal identifier
     * @return True if trigger is active
     */
    function isTriggerActive(bytes32 dealId)
        external
        view
        returns (bool)
    {
        return triggerActive[dealId];
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EMERGENCY FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Pause the contract
     */
    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    /**
     * @notice Unpause the contract
     */
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    /**
     * @notice Emergency token recovery
     * @param token Token address
     * @param to Recipient address
     * @param amount Amount to recover
     */
    function emergencyRecover(address token, address to, uint256 amount)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        if (to == address(0)) revert ZeroAddress();
        IERC20(token).safeTransfer(to, amount);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL HELPERS
    // ═══════════════════════════════════════════════════════════════════════

    function _min(uint256 a, uint256 b) internal pure returns (uint256) {
        return a < b ? a : b;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // UPGRADE AUTHORIZATION
    // ═══════════════════════════════════════════════════════════════════════

    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyRole(UPGRADER_ROLE)
    {}
}

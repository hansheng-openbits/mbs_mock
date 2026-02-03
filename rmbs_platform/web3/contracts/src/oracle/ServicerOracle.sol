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

/**
 * @title ServicerOracle
 * @notice Oracle contract for servicer loan performance data
 * @dev Receives loan-level data from servicers and aggregates for waterfall execution
 * 
 * Key Features:
 * - Multi-servicer support per deal
 * - ZK-proof verification ready (placeholder)
 * - Loan-level performance tracking
 * - Aggregated deal-level metrics
 * - Data staleness protection
 * - Dispute mechanism
 * 
 * Data Flow:
 * 1. Servicer submits loan tape (off-chain → backend)
 * 2. Backend validates and computes ZK proof
 * 3. Servicer/Backend submits aggregated data + proof to oracle
 * 4. Oracle verifies and stores data
 * 5. WaterfallEngine reads data for distribution
 * 
 * Security:
 * - Role-based access control
 * - Data staleness checks
 * - ZK verification (extensible)
 * - Dispute resolution
 * 
 * @custom:security-contact security@rmbs.io
 */
contract ServicerOracle is
    AccessControlUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable
{
    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Role for servicers who can submit data
    bytes32 public constant SERVICER_ROLE = keccak256("SERVICER_ROLE");

    /// @notice Role for validators who can verify data
    bytes32 public constant VALIDATOR_ROLE = keccak256("VALIDATOR_ROLE");

    /// @notice Role for contract upgrades
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice Maximum data staleness (24 hours)
    uint256 public constant MAX_STALENESS = 24 hours;

    /// @notice Dispute period (48 hours)
    uint256 public constant DISPUTE_PERIOD = 48 hours;

    // ═══════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Loan status enum
    enum LoanStatus {
        CURRENT,        // 0-29 days delinquent
        DQ_30,          // 30-59 days delinquent
        DQ_60,          // 60-89 days delinquent
        DQ_90,          // 90+ days delinquent
        FORECLOSURE,    // In foreclosure
        REO,            // Real estate owned
        PAID_OFF,       // Loan paid in full
        MODIFIED,       // Loan modified
        DEFAULTED       // Written off
    }

    /// @notice Aggregated loan tape data for a period
    struct LoanTapeData {
        bytes32 dealId;
        uint256 periodNumber;
        uint256 reportingDate;          // Date of the data
        uint256 submissionTimestamp;    // When submitted on-chain
        
        // Collections
        uint256 scheduledPrincipal;     // Scheduled principal payments
        uint256 scheduledInterest;      // Scheduled interest payments
        uint256 actualPrincipal;        // Actual principal collected
        uint256 actualInterest;         // Actual interest collected
        uint256 prepayments;            // Prepayment amounts (SMM)
        uint256 curtailments;           // Partial prepayments
        
        // Losses
        uint256 defaults;               // New defaults this period
        uint256 lossSeverity;           // Realized losses
        uint256 recoveries;             // Recoveries on defaulted loans
        
        // Pool metrics
        uint256 totalLoanCount;         // Total loans in pool
        uint256 currentLoanCount;       // Loans in current status
        uint256 delinquentLoanCount;    // Loans 30+ DPD
        uint256 totalUPB;               // Total unpaid principal balance
        uint256 wac;                    // Weighted average coupon (bps)
        uint256 wam;                    // Weighted average maturity (months)
        uint256 waLTV;                  // Weighted average LTV (bps = 80% → 8000)
        
        // Verification
        bytes32 dataHash;               // Hash of full loan tape (for ZK)
        bytes zkProof;                  // ZK proof of data validity
        bool isVerified;                // Has been verified
        bool isDisputed;                // Under dispute
        address submitter;              // Who submitted
    }

    /// @notice Servicer registration data
    struct ServicerInfo {
        address servicerAddress;
        string servicerName;
        bool isActive;
        uint256 registrationDate;
        bytes32[] assignedDeals;
    }

    /// @notice Dispute data
    struct Dispute {
        bytes32 dealId;
        uint256 periodNumber;
        address disputant;
        string reason;
        uint256 timestamp;
        bool isResolved;
        bool inFavorOfServicer;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // STORAGE
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Loan tape data by deal and period
    mapping(bytes32 => mapping(uint256 => LoanTapeData)) public loanTapeData;

    /// @notice Current period by deal
    mapping(bytes32 => uint256) public currentPeriod;

    /// @notice Servicer information by address
    mapping(address => ServicerInfo) public servicers;

    /// @notice Assigned servicer for each deal
    mapping(bytes32 => address) public dealServicer;

    /// @notice Disputes by deal and period
    mapping(bytes32 => mapping(uint256 => Dispute)) public disputes;

    /// @notice ZK verifier contract address (for future use)
    address public zkVerifier;

    /// @notice WaterfallEngine contract address
    address public waterfallEngine;

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a servicer is registered
    event ServicerRegistered(
        address indexed servicer,
        string name
    );

    /// @notice Emitted when a servicer is assigned to a deal
    event ServicerAssigned(
        bytes32 indexed dealId,
        address indexed servicer
    );

    /// @notice Emitted when loan tape data is submitted
    event LoanTapeSubmitted(
        bytes32 indexed dealId,
        uint256 indexed period,
        address indexed submitter,
        uint256 actualPrincipal,
        uint256 actualInterest,
        uint256 defaults
    );

    /// @notice Emitted when data is verified
    event DataVerified(
        bytes32 indexed dealId,
        uint256 indexed period,
        address indexed verifier
    );

    /// @notice Emitted when a dispute is filed
    event DisputeFiled(
        bytes32 indexed dealId,
        uint256 indexed period,
        address indexed disputant,
        string reason
    );

    /// @notice Emitted when a dispute is resolved
    event DisputeResolved(
        bytes32 indexed dealId,
        uint256 indexed period,
        bool inFavorOfServicer
    );

    /// @notice Emitted when WaterfallEngine is updated
    event WaterfallEngineUpdated(
        address indexed oldEngine,
        address indexed newEngine
    );

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ZeroAddress();
    error ServicerNotRegistered(address servicer);
    error ServicerNotActive(address servicer);
    error ServicerNotAssigned(bytes32 dealId, address servicer);
    error DealAlreadyAssigned(bytes32 dealId);
    error PeriodAlreadySubmitted(bytes32 dealId, uint256 period);
    error InvalidPeriodSequence(uint256 expected, uint256 provided);
    error DataStale(uint256 reportingDate, uint256 currentTime);
    error DataNotVerified(bytes32 dealId, uint256 period);
    error DataDisputed(bytes32 dealId, uint256 period);
    error DisputePeriodExpired();
    error DisputeAlreadyExists();
    error InvalidZKProof();
    error NotWaterfallEngine();

    // ═══════════════════════════════════════════════════════════════════════
    // MODIFIERS
    // ═══════════════════════════════════════════════════════════════════════

    modifier onlyActiveServicer(bytes32 dealId) {
        ServicerInfo storage info = servicers[msg.sender];
        if (!info.isActive) revert ServicerNotActive(msg.sender);
        if (dealServicer[dealId] != msg.sender) {
            revert ServicerNotAssigned(dealId, msg.sender);
        }
        _;
    }

    modifier onlyWaterfallEngine() {
        if (msg.sender != waterfallEngine) revert NotWaterfallEngine();
        _;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZER
    // ═══════════════════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the oracle
     * @param admin Admin address
     * @param _waterfallEngine WaterfallEngine contract address
     */
    function initialize(address admin, address _waterfallEngine)
        external
        initializer
    {
        if (admin == address(0)) revert ZeroAddress();

        __AccessControl_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(VALIDATOR_ROLE, admin);
        _grantRole(UPGRADER_ROLE, admin);

        waterfallEngine = _waterfallEngine;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SERVICER MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Register a new servicer
     * @param servicerAddress Address of the servicer
     * @param servicerName Human-readable name
     */
    function registerServicer(address servicerAddress, string calldata servicerName)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        if (servicerAddress == address(0)) revert ZeroAddress();

        servicers[servicerAddress] = ServicerInfo({
            servicerAddress: servicerAddress,
            servicerName: servicerName,
            isActive: true,
            registrationDate: block.timestamp,
            assignedDeals: new bytes32[](0)
        });

        _grantRole(SERVICER_ROLE, servicerAddress);

        emit ServicerRegistered(servicerAddress, servicerName);
    }

    /**
     * @notice Deactivate a servicer
     * @param servicerAddress Address of the servicer
     */
    function deactivateServicer(address servicerAddress)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        servicers[servicerAddress].isActive = false;
        _revokeRole(SERVICER_ROLE, servicerAddress);
    }

    /**
     * @notice Assign a servicer to a deal
     * @param dealId Deal identifier
     * @param servicerAddress Servicer address
     */
    function assignServicerToDeal(bytes32 dealId, address servicerAddress)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        if (!servicers[servicerAddress].isActive) {
            revert ServicerNotActive(servicerAddress);
        }
        if (dealServicer[dealId] != address(0)) {
            revert DealAlreadyAssigned(dealId);
        }

        dealServicer[dealId] = servicerAddress;
        servicers[servicerAddress].assignedDeals.push(dealId);

        emit ServicerAssigned(dealId, servicerAddress);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DATA SUBMISSION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Submit loan tape data for a period
     * @param data Aggregated loan tape data
     */
    function submitLoanTape(LoanTapeData calldata data)
        external
        onlyRole(SERVICER_ROLE)
        onlyActiveServicer(data.dealId)
        nonReentrant
        whenNotPaused
    {
        // Validate period sequence
        uint256 expectedPeriod = currentPeriod[data.dealId] + 1;
        if (data.periodNumber != expectedPeriod) {
            revert InvalidPeriodSequence(expectedPeriod, data.periodNumber);
        }

        // Check if already submitted
        if (loanTapeData[data.dealId][data.periodNumber].submissionTimestamp > 0) {
            revert PeriodAlreadySubmitted(data.dealId, data.periodNumber);
        }

        // Validate data freshness
        if (block.timestamp - data.reportingDate > MAX_STALENESS) {
            revert DataStale(data.reportingDate, block.timestamp);
        }

        // Store data
        LoanTapeData storage stored = loanTapeData[data.dealId][data.periodNumber];
        stored.dealId = data.dealId;
        stored.periodNumber = data.periodNumber;
        stored.reportingDate = data.reportingDate;
        stored.submissionTimestamp = block.timestamp;
        
        stored.scheduledPrincipal = data.scheduledPrincipal;
        stored.scheduledInterest = data.scheduledInterest;
        stored.actualPrincipal = data.actualPrincipal;
        stored.actualInterest = data.actualInterest;
        stored.prepayments = data.prepayments;
        stored.curtailments = data.curtailments;
        
        stored.defaults = data.defaults;
        stored.lossSeverity = data.lossSeverity;
        stored.recoveries = data.recoveries;
        
        stored.totalLoanCount = data.totalLoanCount;
        stored.currentLoanCount = data.currentLoanCount;
        stored.delinquentLoanCount = data.delinquentLoanCount;
        stored.totalUPB = data.totalUPB;
        stored.wac = data.wac;
        stored.wam = data.wam;
        stored.waLTV = data.waLTV;
        
        stored.dataHash = data.dataHash;
        stored.zkProof = data.zkProof;
        stored.isVerified = false;
        stored.isDisputed = false;
        stored.submitter = msg.sender;

        // Update current period
        currentPeriod[data.dealId] = data.periodNumber;

        emit LoanTapeSubmitted(
            data.dealId,
            data.periodNumber,
            msg.sender,
            data.actualPrincipal,
            data.actualInterest,
            data.defaults
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VERIFICATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Verify submitted data
     * @param dealId Deal identifier
     * @param period Period number
     */
    function verifyData(bytes32 dealId, uint256 period)
        external
        onlyRole(VALIDATOR_ROLE)
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        // TODO: Add ZK proof verification when zkVerifier is set
        // if (zkVerifier != address(0)) {
        //     if (!IZKVerifier(zkVerifier).verify(data.zkProof, data.dataHash)) {
        //         revert InvalidZKProof();
        //     }
        // }

        data.isVerified = true;

        emit DataVerified(dealId, period, msg.sender);
    }

    /**
     * @notice Auto-verify after dispute period (if no disputes)
     * @param dealId Deal identifier
     * @param period Period number
     */
    function autoVerify(bytes32 dealId, uint256 period) external {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        if (data.isVerified) return;
        if (data.isDisputed) revert DataDisputed(dealId, period);
        if (block.timestamp < data.submissionTimestamp + DISPUTE_PERIOD) {
            revert DisputePeriodExpired();
        }

        data.isVerified = true;
        emit DataVerified(dealId, period, address(0));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DISPUTE MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice File a dispute against submitted data
     * @param dealId Deal identifier
     * @param period Period number
     * @param reason Reason for dispute
     */
    function fileDispute(bytes32 dealId, uint256 period, string calldata reason)
        external
        onlyRole(VALIDATOR_ROLE)
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        if (data.isVerified) revert DataNotVerified(dealId, period);
        if (data.isDisputed) revert DisputeAlreadyExists();
        if (block.timestamp > data.submissionTimestamp + DISPUTE_PERIOD) {
            revert DisputePeriodExpired();
        }

        data.isDisputed = true;
        disputes[dealId][period] = Dispute({
            dealId: dealId,
            periodNumber: period,
            disputant: msg.sender,
            reason: reason,
            timestamp: block.timestamp,
            isResolved: false,
            inFavorOfServicer: false
        });

        emit DisputeFiled(dealId, period, msg.sender, reason);
    }

    /**
     * @notice Resolve a dispute
     * @param dealId Deal identifier
     * @param period Period number
     * @param inFavorOfServicer True if servicer data was correct
     */
    function resolveDispute(bytes32 dealId, uint256 period, bool inFavorOfServicer)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        Dispute storage dispute = disputes[dealId][period];
        LoanTapeData storage data = loanTapeData[dealId][period];

        dispute.isResolved = true;
        dispute.inFavorOfServicer = inFavorOfServicer;

        if (inFavorOfServicer) {
            data.isDisputed = false;
            data.isVerified = true;
        }
        // If not in favor, servicer must resubmit

        emit DisputeResolved(dealId, period, inFavorOfServicer);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // WATERFALL ENGINE INTERFACE
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get collections data for waterfall (called by WaterfallEngine)
     * @param dealId Deal identifier
     * @param period Period number
     * @return interestCollected Total interest collected
     * @return principalCollected Total principal collected
     * @return losses Total realized losses
     * @return prepayments Total prepayments
     */
    function getCollectionsForWaterfall(bytes32 dealId, uint256 period)
        external
        view
        returns (
            uint256 interestCollected,
            uint256 principalCollected,
            uint256 losses,
            uint256 prepayments
        )
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        if (!data.isVerified) revert DataNotVerified(dealId, period);
        if (data.isDisputed) revert DataDisputed(dealId, period);

        interestCollected = data.actualInterest;
        principalCollected = data.actualPrincipal + data.prepayments + data.curtailments;
        losses = data.lossSeverity;
        prepayments = data.prepayments;
    }

    /**
     * @notice Push collections to WaterfallEngine
     * @param dealId Deal identifier
     * @param period Period number
     */
    function pushToWaterfall(bytes32 dealId, uint256 period)
        external
        onlyRole(VALIDATOR_ROLE)
        nonReentrant
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        if (!data.isVerified) revert DataNotVerified(dealId, period);
        if (data.isDisputed) revert DataDisputed(dealId, period);

        // Call WaterfallEngine to report collections
        // Note: WaterfallEngine must grant EXECUTOR_ROLE to this contract
        (bool success,) = waterfallEngine.call(
            abi.encodeWithSignature(
                "reportCollections(bytes32,uint256,uint256,uint256,uint256)",
                dealId,
                data.actualInterest,
                data.actualPrincipal + data.prepayments + data.curtailments,
                data.lossSeverity,
                data.prepayments
            )
        );

        if (!success) revert TransferFailed();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get loan tape data for a period
     * @param dealId Deal identifier
     * @param period Period number
     * @return Loan tape data
     */
    function getLoanTapeData(bytes32 dealId, uint256 period)
        external
        view
        returns (LoanTapeData memory)
    {
        return loanTapeData[dealId][period];
    }

    /**
     * @notice Get current period for a deal
     * @param dealId Deal identifier
     * @return Current period number
     */
    function getDealCurrentPeriod(bytes32 dealId)
        external
        view
        returns (uint256)
    {
        return currentPeriod[dealId];
    }

    /**
     * @notice Get servicer information
     * @param servicerAddress Servicer address
     * @return Servicer info
     */
    function getServicerInfo(address servicerAddress)
        external
        view
        returns (ServicerInfo memory)
    {
        return servicers[servicerAddress];
    }

    /**
     * @notice Get servicer for a deal
     * @param dealId Deal identifier
     * @return Servicer address
     */
    function getServicerForDeal(bytes32 dealId)
        external
        view
        returns (address)
    {
        return dealServicer[dealId];
    }

    /**
     * @notice Check if data is ready for waterfall
     * @param dealId Deal identifier
     * @param period Period number
     * @return True if verified and not disputed
     */
    function isDataReadyForWaterfall(bytes32 dealId, uint256 period)
        external
        view
        returns (bool)
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        return data.isVerified && !data.isDisputed;
    }

    /**
     * @notice Get pool metrics
     * @param dealId Deal identifier
     * @param period Period number
     * @return totalUPB Total unpaid principal balance
     * @return wac Weighted average coupon
     * @return wam Weighted average maturity
     * @return delinquencyRate Delinquency rate (bps)
     */
    function getPoolMetrics(bytes32 dealId, uint256 period)
        external
        view
        returns (
            uint256 totalUPB,
            uint256 wac,
            uint256 wam,
            uint256 delinquencyRate
        )
    {
        LoanTapeData storage data = loanTapeData[dealId][period];
        
        totalUPB = data.totalUPB;
        wac = data.wac;
        wam = data.wam;
        
        if (data.totalLoanCount > 0) {
            delinquencyRate = (data.delinquentLoanCount * 10000) / data.totalLoanCount;
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Set ZK verifier contract
     * @param _zkVerifier New verifier address
     */
    function setZKVerifier(address _zkVerifier)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        zkVerifier = _zkVerifier;
    }

    /**
     * @notice Set WaterfallEngine contract
     * @param _waterfallEngine New engine address
     */
    function setWaterfallEngine(address _waterfallEngine)
        external
        onlyRole(DEFAULT_ADMIN_ROLE)
    {
        address old = waterfallEngine;
        waterfallEngine = _waterfallEngine;
        emit WaterfallEngineUpdated(old, _waterfallEngine);
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

    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL
    // ═══════════════════════════════════════════════════════════════════════

    error TransferFailed();

    // ═══════════════════════════════════════════════════════════════════════
    // UPGRADE AUTHORIZATION
    // ═══════════════════════════════════════════════════════════════════════

    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyRole(UPGRADER_ROLE)
    {}
}

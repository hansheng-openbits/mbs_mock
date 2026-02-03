// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC20Upgradeable} from "@openzeppelin/contracts-upgradeable/token/ERC20/ERC20Upgradeable.sol";
import {ERC20SnapshotUpgradeable} from
    "@openzeppelin/contracts-upgradeable/token/ERC20/extensions/ERC20SnapshotUpgradeable.sol";
import {AccessControlUpgradeable} from
    "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {UUPSUpgradeable} from
    "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {ReentrancyGuardUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {IERC1400} from "../interfaces/IERC1400.sol";
import {ITransferValidator} from "../interfaces/ITransferValidator.sol";

/**
 * @title RMBSTranche
 * @notice ERC-1400 compliant security token representing a tranche in an RMBS deal
 * @dev Implements transfer restrictions, yield distribution, and factor-based paydowns
 * 
 * Key Features:
 * - ERC-20 compatible with added security token features
 * - Transfer restrictions via pluggable validator
 * - Pull-based yield distribution (gas efficient)
 * - Factor-based principal paydowns
 * - Document management (IPFS links)
 * - Controller operations (forced transfers for regulatory compliance)
 * - Circuit breaker (pause mechanism)
 * - UUPS upgradeable
 * 
 * Security:
 * - ReentrancyGuard on all state-changing functions
 * - Access control for all sensitive operations
 * - Checks-effects-interactions pattern
 * - Emergency pause functionality
 * 
 * Gas Optimization:
 * - Bitmap for boolean flags
 * - Packed struct storage
 * - View functions for complex calculations
 * 
 * @custom:security-contact security@rmbs.io
 */
contract RMBSTranche is
    ERC20SnapshotUpgradeable,
    AccessControlUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    IERC1400
{
    using SafeERC20 for IERC20;

    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Role for issuer operations (minting, document management)
    bytes32 public constant ISSUER_ROLE = keccak256("ISSUER_ROLE");

    /// @notice Role for trustee operations (waterfall execution, factor updates)
    bytes32 public constant TRUSTEE_ROLE = keccak256("TRUSTEE_ROLE");

    /// @notice Role for controller operations (forced transfers)
    bytes32 public constant CONTROLLER_ROLE = keccak256("CONTROLLER_ROLE");

    /// @notice Role for contract upgrades
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice 100% represented as 1e18 (1.0 = 100%)
    uint256 public constant FACTOR_PRECISION = 1e18;

    /// @notice 100% in basis points
    uint256 public constant BPS_DENOMINATOR = 10_000;

    /// @notice Maximum periods that can be claimed in one transaction (prevents DoS)
    uint256 public constant MAX_CLAIM_PERIODS = 100;

    /// @notice ESC (Ethereum Status Code) for successful transfer
    bytes1 public constant ESC_51 = 0x51;

    /// @notice ESC for insufficient balance
    bytes1 public constant ESC_52 = 0x52;

    /// @notice ESC for transfer restricted
    bytes1 public constant ESC_54 = 0x54;

    // ═══════════════════════════════════════════════════════════════════════
    // STATE VARIABLES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Unique identifier for the deal this tranche belongs to
    bytes32 public dealId;

    /// @notice Tranche identifier (e.g., "A1", "M1", "B1")
    string public trancheId;

    /// @notice Original face value at issuance (never changes)
    uint256 public originalFaceValue;

    /// @notice Current factor (1e18 = 100%, decreases with principal paydowns)
    uint256 public currentFactor;

    /// @notice Coupon rate in basis points (e.g., 550 = 5.50%)
    uint256 public couponRateBps;

    /// @notice Payment frequency (1 = monthly, 3 = quarterly, 6 = semi-annual, 12 = annual)
    uint8 public paymentFrequency;

    /// @notice Legal maturity date (Unix timestamp)
    uint256 public maturityDate;

    /// @notice Transfer validator contract for compliance checks
    ITransferValidator public transferValidator;

    /// @notice Payment token (typically USDC)
    IERC20 public paymentToken;

    /// @notice Current period number (increments with each distribution)
    uint256 public currentPeriod;

    /// @notice Whether the contract is paused (circuit breaker)
    bool public paused;

    /// @notice Whether controller operations are enabled
    bool public controllable;

    // ═══════════════════════════════════════════════════════════════════════
    // MAPPINGS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Document storage (name => DocumentInfo)
    mapping(bytes32 => DocumentInfo) public documents;

    /// @notice Array of document names for enumeration
    bytes32[] public documentNames;

    /// @notice Total yield distributed per period
    mapping(uint256 => uint256) public periodYield;

    /// @notice Last period for which a holder has claimed yield
    mapping(address => uint256) public lastClaimedPeriod;

    /// @notice Snapshot ID for each period (record date)
    mapping(uint256 => uint256) public periodSnapshotId;

    // ═══════════════════════════════════════════════════════════════════════
    // STRUCTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Document metadata
    struct DocumentInfo {
        string uri; // IPFS hash or URL
        bytes32 documentHash; // Hash of document content for integrity
        uint256 timestamp; // Last updated timestamp
    }

    /// @notice Parameters for tranche initialization
    struct InitParams {
        bytes32 dealId;
        string trancheId;
        string name;
        string symbol;
        uint256 originalFaceValue;
        uint256 couponRateBps;
        uint8 paymentFrequency;
        uint256 maturityDate;
        address paymentToken;
        address transferValidator;
        address admin;
        address issuer;
        address trustee;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Factor updated after principal paydown
    event FactorUpdated(uint256 indexed period, uint256 oldFactor, uint256 newFactor);

    /// @notice Yield distributed for a period
    event YieldDistributed(uint256 indexed period, uint256 amount, uint256 snapshotId);

    /// @notice Investor claimed yield
    event YieldClaimed(
        address indexed holder, uint256 amount, uint256 fromPeriod, uint256 toPeriod
    );

    /// @notice Principal paid down
    event PrincipalPaydown(uint256 indexed period, uint256 amount, uint256 newFactor);

    /// @notice Contract paused
    event Paused(address indexed by);

    /// @notice Contract unpaused
    event Unpaused(address indexed by);

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ContractPaused();
    error TransferRestricted(bytes1 reasonCode, string message);
    error InvalidFactor(uint256 provided, uint256 current);
    error NothingToClaim();
    error InvalidPeriod(uint256 provided, uint256 current);
    error ZeroAddress();
    error ZeroAmount();
    error InvalidCouponRate(uint256 provided);
    error InvalidPaymentFrequency(uint8 provided);
    error MaturityDateInPast(uint256 provided);
    error InsufficientBalance(uint256 requested, uint256 available);
    error TooManyPeriodsToProcess(uint256 requested, uint256 max);

    // ═══════════════════════════════════════════════════════════════════════
    // MODIFIERS
    // ═══════════════════════════════════════════════════════════════════════

    modifier whenNotPaused() {
        if (paused) revert ContractPaused();
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
     * @notice Initialize the tranche contract
     * @param params Tranche configuration parameters (includes admin, issuer, trustee)
     */
    function initialize(InitParams calldata params)
        external
        initializer
    {
        // Input validation
        if (params.admin == address(0) || params.issuer == address(0) || params.trustee == address(0)) {
            revert ZeroAddress();
        }
        if (params.originalFaceValue == 0) revert ZeroAmount();
        if (params.couponRateBps > BPS_DENOMINATOR) revert InvalidCouponRate(params.couponRateBps);
        if (
            params.paymentFrequency != 1 && params.paymentFrequency != 3
                && params.paymentFrequency != 6 && params.paymentFrequency != 12
        ) {
            revert InvalidPaymentFrequency(params.paymentFrequency);
        }
        if (params.maturityDate <= block.timestamp) {
            revert MaturityDateInPast(params.maturityDate);
        }
        if (params.paymentToken == address(0) || params.transferValidator == address(0)) {
            revert ZeroAddress();
        }

        // Initialize parent contracts
        __ERC20_init(params.name, params.symbol);
        __ERC20Snapshot_init();
        __AccessControl_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();

        // Set state variables
        dealId = params.dealId;
        trancheId = params.trancheId;
        originalFaceValue = params.originalFaceValue;
        currentFactor = FACTOR_PRECISION; // 100%
        couponRateBps = params.couponRateBps;
        paymentFrequency = params.paymentFrequency;
        maturityDate = params.maturityDate;
        paymentToken = IERC20(params.paymentToken);
        transferValidator = ITransferValidator(params.transferValidator);
        controllable = true;

        // Grant roles
        _grantRole(DEFAULT_ADMIN_ROLE, params.admin);
        _grantRole(ISSUER_ROLE, params.issuer);
        _grantRole(TRUSTEE_ROLE, params.trustee);
        _grantRole(UPGRADER_ROLE, params.admin);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ERC-1400: TRANSFER VALIDATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Check if a transfer is allowed
     * @param from Sender address
     * @param to Recipient address
     * @param value Amount to transfer
     * @return ESC (Ethereum Status Code)
     * @return message Human-readable reason
     */
    function canTransfer(address from, address to, uint256 value)
        public
        view
        returns (bytes1 ESC, string memory message)
    {
        // Check if contract is paused
        if (paused) {
            return (ESC_54, "Contract paused");
        }

        // Check balance
        if (balanceOf(from) < value) {
            return (ESC_52, "Insufficient balance");
        }

        // Check compliance via transfer validator
        (bool valid, bytes1 code, string memory validatorMessage) =
            transferValidator.validateTransfer(dealId, from, to, value);

        if (!valid) {
            return (code, validatorMessage);
        }

        return (ESC_51, "Transfer allowed");
    }

    /**
     * @notice Override _beforeTokenTransfer to enforce transfer restrictions
     * @dev Called on mint, burn, and transfer
     */
    function _beforeTokenTransfer(address from, address to, uint256 amount)
        internal
        virtual
        override
        whenNotPaused
    {
        // Skip validation for mints and burns
        if (from != address(0) && to != address(0)) {
            (bytes1 code, string memory message) = canTransfer(from, to, amount);
            if (code != ESC_51) {
                revert TransferRestricted(code, message);
            }
        }

        // Call parent for snapshot logic
        super._beforeTokenTransfer(from, to, amount);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ERC-1400: ISSUANCE & REDEMPTION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Issue new tokens (ERC-1400 compliant)
     * @param tokenHolder Address to receive tokens
     * @param value Amount to issue (1 token = $1 face value)
     * @param data Additional data (unused)
     */
    function issue(address tokenHolder, uint256 value, bytes calldata data)
        external
        override
        onlyRole(ISSUER_ROLE)
        nonReentrant
    {
        if (tokenHolder == address(0)) revert ZeroAddress();
        if (value == 0) revert ZeroAmount();

        _mint(tokenHolder, value);

        emit Issued(msg.sender, tokenHolder, value, data);
    }

    /**
     * @notice Issue new tokens (convenience method without data)
     * @param tokenHolder Address to receive tokens
     * @param value Amount to issue (1 token = $1 face value)
     */
    function issue(address tokenHolder, uint256 value)
        external
        onlyRole(ISSUER_ROLE)
        nonReentrant
    {
        if (tokenHolder == address(0)) revert ZeroAddress();
        if (value == 0) revert ZeroAmount();

        _mint(tokenHolder, value);

        emit Issued(msg.sender, tokenHolder, value, "");
    }

    /**
     * @notice Redeem tokens (ERC-1400 compliant)
     * @param value Amount to redeem
     * @param data Additional data (unused)
     */
    function redeem(uint256 value, bytes calldata data) external override nonReentrant {
        _redeemInternal(value, data);
    }

    /**
     * @notice Redeem tokens (convenience method without data)
     * @param value Amount to redeem
     */
    function redeem(uint256 value) external nonReentrant {
        _redeemInternal(value, "");
    }

    function _redeemInternal(uint256 value, bytes memory data) internal {
        if (value == 0) revert ZeroAmount();
        if (balanceOf(msg.sender) < value) {
            revert InsufficientBalance(value, balanceOf(msg.sender));
        }

        _burn(msg.sender, value);

        emit Redeemed(msg.sender, msg.sender, value, data);
    }

    /**
     * @notice Redeem tokens from a holder (trustee operation)
     * @param tokenHolder Address to redeem from
     * @param value Amount to redeem
     * @param data Additional data
     */
    function redeemFrom(address tokenHolder, uint256 value, bytes calldata data)
        external
        onlyRole(TRUSTEE_ROLE)
        nonReentrant
    {
        if (tokenHolder == address(0)) revert ZeroAddress();
        if (value == 0) revert ZeroAmount();
        if (balanceOf(tokenHolder) < value) {
            revert InsufficientBalance(value, balanceOf(tokenHolder));
        }

        _burn(tokenHolder, value);

        emit Redeemed(msg.sender, tokenHolder, value, data);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FACTOR & PRINCIPAL PAYDOWN
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Update factor after principal paydown
     * @dev Called by WaterfallEngine after each distribution period
     * @param newFactor New factor (e.g., 0.95e18 = 95% remaining)
     */
    function updateFactor(uint256 newFactor)
        external
        onlyRole(TRUSTEE_ROLE)
        nonReentrant
    {
        // Validate factor
        if (newFactor > currentFactor || newFactor > FACTOR_PRECISION) {
            revert InvalidFactor(newFactor, currentFactor);
        }

        uint256 oldFactor = currentFactor;
        currentFactor = newFactor;
        currentPeriod++;

        emit FactorUpdated(currentPeriod, oldFactor, newFactor);
        emit PrincipalPaydown(
            currentPeriod, originalFaceValue * (oldFactor - newFactor) / FACTOR_PRECISION, newFactor
        );
    }

    /**
     * @notice Get current face value for a holder based on factor
     * @param holder Token holder address
     * @return Current face value in payment token decimals
     */
    function currentFaceValueOf(address holder) public view returns (uint256) {
        return balanceOf(holder) * currentFactor / FACTOR_PRECISION;
    }

    /**
     * @notice Get total current face value based on factor
     * @return Total current face value
     */
    function totalCurrentFaceValue() public view returns (uint256) {
        return originalFaceValue * currentFactor / FACTOR_PRECISION;
    }

    /**
     * @notice Alias for totalCurrentFaceValue (backward compatibility)
     */
    function currentFaceValue() public view returns (uint256) {
        return totalCurrentFaceValue();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // YIELD DISTRIBUTION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Distribute yield for a period (called by WaterfallEngine)
     * @dev Takes snapshot atomically to establish record date
     * @param amount Total yield amount for this tranche this period
     */
    function distributeYield(uint256 amount)
        external
        onlyRole(TRUSTEE_ROLE)
        nonReentrant
    {
        if (amount == 0) revert ZeroAmount();

        // Transfer payment tokens to this contract
        paymentToken.safeTransferFrom(msg.sender, address(this), amount);

        // Take snapshot ATOMICALLY - this is the "record date"
        // Whoever holds tokens at this moment gets the yield for this period
        uint256 snapshotId = _snapshot();
        periodSnapshotId[currentPeriod] = snapshotId;

        // Store yield for this period
        periodYield[currentPeriod] = amount;

        emit YieldDistributed(currentPeriod, amount, snapshotId);
    }

    /**
     * @notice Claim accumulated yield (pull-based)
     * @dev Calculates pro-rata share based on balance snapshots
     */
    function claimYield() external nonReentrant whenNotPaused {
        uint256 lastClaimed = lastClaimedPeriod[msg.sender];
        uint256 periodsToClaim = currentPeriod - lastClaimed;

        // Prevent DoS via excessive loop iterations
        if (periodsToClaim > MAX_CLAIM_PERIODS) {
            revert TooManyPeriodsToProcess(periodsToClaim, MAX_CLAIM_PERIODS);
        }

        uint256 claimable = _calculateClaimableYield(msg.sender);

        if (claimable == 0) revert NothingToClaim();

        uint256 fromPeriod = lastClaimed + 1;
        lastClaimedPeriod[msg.sender] = currentPeriod;

        paymentToken.safeTransfer(msg.sender, claimable);

        emit YieldClaimed(msg.sender, claimable, fromPeriod, currentPeriod);
    }

    /**
     * @notice Calculate claimable yield for a holder
     * @param holder Token holder address
     * @return Total claimable yield
     */
    function claimableYield(address holder) external view returns (uint256) {
        return _calculateClaimableYield(holder);
    }

    /**
     * @notice Claim yield for specific periods (for holders with >100 unclaimed periods)
     * @param toPeriod Period to claim up to (inclusive)
     * @dev Allows claiming in batches if total unclaimed exceeds MAX_CLAIM_PERIODS
     */
    function claimYieldUpTo(uint256 toPeriod) external nonReentrant whenNotPaused {
        if (toPeriod > currentPeriod) revert InvalidPeriod(toPeriod, currentPeriod);
        
        uint256 lastClaimed = lastClaimedPeriod[msg.sender];
        if (toPeriod <= lastClaimed) revert InvalidPeriod(toPeriod, lastClaimed);

        uint256 periodsToClaim = toPeriod - lastClaimed;
        
        // Still enforce max periods per transaction
        if (periodsToClaim > MAX_CLAIM_PERIODS) {
            revert TooManyPeriodsToProcess(periodsToClaim, MAX_CLAIM_PERIODS);
        }

        uint256 claimable = _calculateClaimableYieldUpTo(msg.sender, toPeriod);

        if (claimable == 0) revert NothingToClaim();

        uint256 fromPeriod = lastClaimed + 1;
        lastClaimedPeriod[msg.sender] = toPeriod;

        paymentToken.safeTransfer(msg.sender, claimable);

        emit YieldClaimed(msg.sender, claimable, fromPeriod, toPeriod);
    }

    /**
     * @notice Internal function to calculate claimable yield
     * @param holder Token holder address
     * @return Total claimable yield across all unclaimed periods
     * @dev Uses ERC20Snapshot to get balance at record date (snapshot)
     */
    function _calculateClaimableYield(address holder) internal view returns (uint256) {
        return _calculateClaimableYieldUpTo(holder, currentPeriod);
    }

    /**
     * @notice Internal function to calculate claimable yield up to a specific period
     * @param holder Token holder address
     * @param toPeriod Last period to include (inclusive)
     * @return Total claimable yield from last claimed period to toPeriod
     * @dev Uses ERC20Snapshot to prevent snapshot gaming attacks
     */
    function _calculateClaimableYieldUpTo(address holder, uint256 toPeriod) internal view returns (uint256) {
        uint256 lastClaimed = lastClaimedPeriod[holder];
        uint256 totalClaimable = 0;

        // Sum yield for all unclaimed periods up to toPeriod
        for (uint256 period = lastClaimed + 1; period <= toPeriod; period++) {
            uint256 periodTotal = periodYield[period];
            uint256 snapshotId = periodSnapshotId[period];

            // Skip if no yield for this period or no snapshot taken
            if (periodTotal == 0 || snapshotId == 0) continue;

            // Get holder's balance at the snapshot (record date)
            // This prevents snapshot gaming: balance is locked at distributeYield() call
            uint256 holderBalance = balanceOfAt(holder, snapshotId);
            
            // Skip if holder had no tokens at record date
            if (holderBalance == 0) continue;

            // Get total supply at the snapshot
            uint256 totalSupplyAtSnapshot = totalSupplyAt(snapshotId);

            // Pro-rata share: (holder balance at snapshot / total supply at snapshot) * period yield
            uint256 share = (holderBalance * periodTotal) / totalSupplyAtSnapshot;
            totalClaimable += share;
        }

        return totalClaimable;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ERC-1400: DOCUMENT MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Set or update a document
     * @param name Document identifier (e.g., keccak256("PROSPECTUS"))
     * @param uri Document URI (IPFS hash or URL)
     * @param documentHash Hash of document content for integrity verification
     */
    function setDocument(bytes32 name, string calldata uri, bytes32 documentHash)
        external
        onlyRole(ISSUER_ROLE)
    {
        // Add to names array if new document
        if (documents[name].timestamp == 0) {
            documentNames.push(name);
        }

        documents[name] = DocumentInfo({uri: uri, documentHash: documentHash, timestamp: block.timestamp});

        emit Document(name, uri, documentHash);  // Document is the event from IERC1400
    }

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
        returns (string memory uri, bytes32 documentHash, uint256 timestamp)
    {
        DocumentInfo memory doc = documents[name];
        return (doc.uri, doc.documentHash, doc.timestamp);
    }

    /**
     * @notice Get all document names
     * @return Array of document identifiers
     */
    function getAllDocuments() external view returns (bytes32[] memory) {
        return documentNames;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ERC-1400: CONTROLLER OPERATIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Force transfer (for legal/regulatory compliance)
     * @dev Only callable by CONTROLLER_ROLE (e.g., court order)
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
    ) external onlyRole(CONTROLLER_ROLE) {
        if (!controllable) revert("Controller operations disabled");
        if (from == address(0) || to == address(0)) revert ZeroAddress();
        if (value == 0) revert ZeroAmount();

        _transfer(from, to, value);

        emit ControllerTransfer(msg.sender, from, to, value, data, operatorData);
    }

    /**
     * @notice Force redemption (for regulatory seizure)
     * @param tokenHolder Address to redeem from
     * @param value Amount to redeem
     * @param data Additional data
     * @param operatorData Operator data (reason)
     */
    function controllerRedeem(
        address tokenHolder,
        uint256 value,
        bytes calldata data,
        bytes calldata operatorData
    ) external onlyRole(CONTROLLER_ROLE) {
        if (!controllable) revert("Controller operations disabled");
        if (tokenHolder == address(0)) revert ZeroAddress();
        if (value == 0) revert ZeroAmount();

        _burn(tokenHolder, value);

        emit ControllerRedemption(msg.sender, tokenHolder, value, data, operatorData);
    }

    /**
     * @notice Check if controller operations are enabled
     * @return true if controllable
     */
    function isControllable() external view returns (bool) {
        return controllable;
    }

    /**
     * @notice Disable controller operations permanently
     * @dev One-way operation - cannot be re-enabled
     */
    function disableController() external onlyRole(DEFAULT_ADMIN_ROLE) {
        controllable = false;
    }

    /**
     * @notice Enable/disable controller operations (for testing)
     * @param enabled Whether controller operations are enabled
     */
    function setControllerEnabled(bool enabled) external onlyRole(DEFAULT_ADMIN_ROLE) {
        controllable = enabled;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CIRCUIT BREAKER
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Pause contract (emergency stop)
     */
    function pause() external onlyRole(TRUSTEE_ROLE) {
        paused = true;
        emit Paused(msg.sender);
    }

    /**
     * @notice Unpause contract
     */
    function unpause() external onlyRole(TRUSTEE_ROLE) {
        paused = false;
        emit Unpaused(msg.sender);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get comprehensive tranche information
     * @return _dealId Deal identifier
     * @return _trancheId Tranche identifier
     * @return _originalFaceValue Original face value
     * @return _currentFactor Current factor
     * @return _couponRateBps Coupon rate in basis points
     * @return _paymentFrequency Payment frequency
     * @return _maturityDate Maturity date
     * @return _currentPeriod Current period
     * @return _paused Whether contract is paused
     */
    function getTrancheInfo()
        external
        view
        returns (
            bytes32 _dealId,
            string memory _trancheId,
            uint256 _originalFaceValue,
            uint256 _currentFactor,
            uint256 _couponRateBps,
            uint8 _paymentFrequency,
            uint256 _maturityDate,
            uint256 _currentPeriod,
            bool _paused
        )
    {
        return (
            dealId,
            trancheId,
            originalFaceValue,
            currentFactor,
            couponRateBps,
            paymentFrequency,
            maturityDate,
            currentPeriod,
            paused
        );
    }

    /**
     * @notice Get snapshot information for a period
     * @param period Period number
     * @return snapshotId The snapshot ID (record date)
     * @return yieldAmount Total yield for the period
     * @return totalSupplyAtSnapshot Total token supply at snapshot
     * @dev Used to verify yield calculations
     */
    function getPeriodSnapshot(uint256 period)
        external
        view
        returns (uint256 snapshotId, uint256 yieldAmount, uint256 totalSupplyAtSnapshot)
    {
        snapshotId = periodSnapshotId[period];
        yieldAmount = periodYield[period];
        totalSupplyAtSnapshot = snapshotId > 0 ? totalSupplyAt(snapshotId) : 0;
    }

    /**
     * @notice Get holder's balance at a specific period's record date
     * @param holder Token holder address
     * @param period Period number
     * @return Balance at the period's snapshot (record date)
     * @dev Returns 0 if period has no snapshot or holder had no tokens
     */
    function getBalanceAtPeriod(address holder, uint256 period)
        external
        view
        returns (uint256)
    {
        uint256 snapshotId = periodSnapshotId[period];
        if (snapshotId == 0) return 0;
        return balanceOfAt(holder, snapshotId);
    }

    /**
     * @notice Get detailed yield information for a holder
     * @param holder Token holder address
     * @return claimable Total claimable yield
     * @return lastClaimed Last period claimed
     * @return unclaimedPeriods Number of periods with unclaimed yield
     */
    function getYieldInfo(address holder)
        external
        view
        returns (uint256 claimable, uint256 lastClaimed, uint256 unclaimedPeriods)
    {
        claimable = _calculateClaimableYield(holder);
        lastClaimed = lastClaimedPeriod[holder];
        unclaimedPeriods = currentPeriod > lastClaimed ? currentPeriod - lastClaimed : 0;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // UPGRADEABILITY
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Authorize contract upgrade
     * @dev Only UPGRADER_ROLE can upgrade
     */
    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyRole(UPGRADER_ROLE)
    {}
}

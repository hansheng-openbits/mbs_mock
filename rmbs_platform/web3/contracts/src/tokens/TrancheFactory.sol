// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {AccessControlUpgradeable} from
    "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {UUPSUpgradeable} from
    "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {ReentrancyGuardUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";
import {RMBSTranche} from "./RMBSTranche.sol";
import {ITransferValidator} from "../interfaces/ITransferValidator.sol";

/**
 * @title TrancheFactory
 * @notice Factory contract for deploying RMBSTranche tokens
 * @dev Implements factory pattern with UUPS upgradeable proxies for each tranche
 * 
 * Key Features:
 * - Deploy new tranches for RMBS deals
 * - Track all deployed tranches by deal
 * - Consistent configuration across tranches
 * - Upgrade management for tranche implementations
 * 
 * Security:
 * - Role-based access control
 * - Input validation
 * - Event emission for all deployments
 * - NonReentrant protection
 * 
 * @custom:security-contact security@rmbs.io
 */
contract TrancheFactory is
    AccessControlUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable
{
    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Role for deploying new tranches
    bytes32 public constant DEPLOYER_ROLE = keccak256("DEPLOYER_ROLE");

    /// @notice Role for contract upgrades
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice Role for updating configurations
    bytes32 public constant CONFIG_ROLE = keccak256("CONFIG_ROLE");

    // ═══════════════════════════════════════════════════════════════════════
    // STORAGE
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Implementation contract address for tranches
    address public trancheImplementation;

    /// @notice Default transfer validator for new tranches
    address public defaultTransferValidator;

    /// @notice All tranches deployed by this factory
    address[] public allTranches;

    /// @notice Tranches by deal ID
    mapping(bytes32 => address[]) public tranchesByDeal;

    /// @notice Tranche address by deal ID and tranche ID
    mapping(bytes32 => mapping(string => address)) public trancheByDealAndId;

    /// @notice Whether an address is a tranche deployed by this factory
    mapping(address => bool) public isDeployedTranche;

    /// @notice Deal metadata
    struct DealInfo {
        bytes32 dealId;
        string name;
        address arranger;
        uint256 closingDate;
        uint256 maturityDate;
        bool isActive;
        uint256 totalFaceValue;
    }

    /// @notice Deal information by deal ID
    mapping(bytes32 => DealInfo) public deals;

    /// @notice All deal IDs
    bytes32[] public allDeals;

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a new deal is registered
    event DealRegistered(
        bytes32 indexed dealId,
        string name,
        address indexed arranger,
        uint256 closingDate,
        uint256 maturityDate
    );

    /// @notice Emitted when a new tranche is deployed
    event TrancheDeployed(
        bytes32 indexed dealId,
        string trancheId,
        address indexed trancheAddress,
        address indexed deployer,
        uint256 originalFaceValue
    );

    /// @notice Emitted when tranche implementation is updated
    event ImplementationUpdated(
        address indexed oldImplementation,
        address indexed newImplementation
    );

    /// @notice Emitted when default validator is updated
    event DefaultValidatorUpdated(
        address indexed oldValidator,
        address indexed newValidator
    );

    /// @notice Emitted when a deal is closed
    event DealClosed(bytes32 indexed dealId, uint256 timestamp);

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ZeroAddress();
    error DealAlreadyExists(bytes32 dealId);
    error DealNotFound(bytes32 dealId);
    error DealNotActive(bytes32 dealId);
    error TrancheAlreadyExists(bytes32 dealId, string trancheId);
    error InvalidMaturityDate(uint256 provided, uint256 dealMaturity);
    error InvalidFaceValue(uint256 provided);
    error ImplementationNotSet();

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZER
    // ═══════════════════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the factory
     * @param admin Admin address with DEFAULT_ADMIN_ROLE
     * @param _trancheImplementation Initial tranche implementation address
     * @param _defaultTransferValidator Default transfer validator address
     */
    function initialize(
        address admin,
        address _trancheImplementation,
        address _defaultTransferValidator
    ) external initializer {
        if (admin == address(0)) revert ZeroAddress();
        if (_trancheImplementation == address(0)) revert ZeroAddress();

        __AccessControl_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(DEPLOYER_ROLE, admin);
        _grantRole(UPGRADER_ROLE, admin);
        _grantRole(CONFIG_ROLE, admin);

        trancheImplementation = _trancheImplementation;
        defaultTransferValidator = _defaultTransferValidator;

        emit ImplementationUpdated(address(0), _trancheImplementation);
        if (_defaultTransferValidator != address(0)) {
            emit DefaultValidatorUpdated(address(0), _defaultTransferValidator);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Register a new RMBS deal
     * @param dealId Unique deal identifier
     * @param name Human-readable deal name
     * @param arranger Deal arranger address
     * @param closingDate Deal closing date timestamp
     * @param maturityDate Deal maturity date timestamp
     */
    function registerDeal(
        bytes32 dealId,
        string calldata name,
        address arranger,
        uint256 closingDate,
        uint256 maturityDate
    ) external onlyRole(DEPLOYER_ROLE) {
        if (dealId == bytes32(0)) revert DealNotFound(dealId);
        if (deals[dealId].dealId != bytes32(0)) revert DealAlreadyExists(dealId);
        if (arranger == address(0)) revert ZeroAddress();
        if (maturityDate <= closingDate) revert InvalidMaturityDate(maturityDate, closingDate);

        deals[dealId] = DealInfo({
            dealId: dealId,
            name: name,
            arranger: arranger,
            closingDate: closingDate,
            maturityDate: maturityDate,
            isActive: true,
            totalFaceValue: 0
        });

        allDeals.push(dealId);

        emit DealRegistered(dealId, name, arranger, closingDate, maturityDate);
    }

    /**
     * @notice Close a deal (no more tranches can be added)
     * @param dealId Deal identifier
     */
    function closeDeal(bytes32 dealId) external onlyRole(DEPLOYER_ROLE) {
        DealInfo storage deal = deals[dealId];
        if (deal.dealId == bytes32(0)) revert DealNotFound(dealId);
        
        deal.isActive = false;
        
        emit DealClosed(dealId, block.timestamp);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TRANCHE DEPLOYMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Deploy a new tranche for a deal
     * @param params Tranche initialization parameters
     * @return trancheAddress Address of the deployed tranche
     */
    function deployTranche(RMBSTranche.InitParams calldata params)
        external
        onlyRole(DEPLOYER_ROLE)
        nonReentrant
        returns (address trancheAddress)
    {
        // Validate implementation is set
        if (trancheImplementation == address(0)) revert ImplementationNotSet();

        // Validate deal exists and is active
        DealInfo storage deal = deals[params.dealId];
        if (deal.dealId == bytes32(0)) revert DealNotFound(params.dealId);
        if (!deal.isActive) revert DealNotActive(params.dealId);

        // Validate tranche doesn't already exist
        if (trancheByDealAndId[params.dealId][params.trancheId] != address(0)) {
            revert TrancheAlreadyExists(params.dealId, params.trancheId);
        }

        // Validate maturity date
        if (params.maturityDate > deal.maturityDate) {
            revert InvalidMaturityDate(params.maturityDate, deal.maturityDate);
        }

        // Validate face value
        if (params.originalFaceValue == 0) revert InvalidFaceValue(0);

        // Deploy proxy with implementation
        bytes memory initData = abi.encodeWithSelector(
            RMBSTranche.initialize.selector,
            params
        );

        ERC1967Proxy proxy = new ERC1967Proxy(trancheImplementation, initData);
        trancheAddress = address(proxy);

        // Note: TransferValidator is set via InitParams.transferValidator during initialize()

        // Update storage
        allTranches.push(trancheAddress);
        tranchesByDeal[params.dealId].push(trancheAddress);
        trancheByDealAndId[params.dealId][params.trancheId] = trancheAddress;
        isDeployedTranche[trancheAddress] = true;
        deal.totalFaceValue += params.originalFaceValue;

        emit TrancheDeployed(
            params.dealId,
            params.trancheId,
            trancheAddress,
            msg.sender,
            params.originalFaceValue
        );
    }

    /**
     * @notice Deploy multiple tranches for a deal in one transaction
     * @param paramsArray Array of tranche initialization parameters
     * @return trancheAddresses Array of deployed tranche addresses
     */
    function deployTranches(RMBSTranche.InitParams[] calldata paramsArray)
        external
        onlyRole(DEPLOYER_ROLE)
        nonReentrant
        returns (address[] memory trancheAddresses)
    {
        trancheAddresses = new address[](paramsArray.length);

        for (uint256 i = 0; i < paramsArray.length; i++) {
            trancheAddresses[i] = _deployTrancheInternal(paramsArray[i]);
        }
    }

    /**
     * @notice Internal function to deploy a tranche
     * @param params Tranche initialization parameters
     * @return trancheAddress Address of the deployed tranche
     */
    function _deployTrancheInternal(RMBSTranche.InitParams calldata params)
        internal
        returns (address trancheAddress)
    {
        // Validate implementation is set
        if (trancheImplementation == address(0)) revert ImplementationNotSet();

        // Validate deal exists and is active
        DealInfo storage deal = deals[params.dealId];
        if (deal.dealId == bytes32(0)) revert DealNotFound(params.dealId);
        if (!deal.isActive) revert DealNotActive(params.dealId);

        // Validate tranche doesn't already exist
        if (trancheByDealAndId[params.dealId][params.trancheId] != address(0)) {
            revert TrancheAlreadyExists(params.dealId, params.trancheId);
        }

        // Validate maturity date
        if (params.maturityDate > deal.maturityDate) {
            revert InvalidMaturityDate(params.maturityDate, deal.maturityDate);
        }

        // Validate face value
        if (params.originalFaceValue == 0) revert InvalidFaceValue(0);

        // Deploy proxy with implementation
        bytes memory initData = abi.encodeWithSelector(
            RMBSTranche.initialize.selector,
            params
        );

        ERC1967Proxy proxy = new ERC1967Proxy(trancheImplementation, initData);
        trancheAddress = address(proxy);

        // Note: TransferValidator is set via InitParams.transferValidator during initialize()

        // Update storage
        allTranches.push(trancheAddress);
        tranchesByDeal[params.dealId].push(trancheAddress);
        trancheByDealAndId[params.dealId][params.trancheId] = trancheAddress;
        isDeployedTranche[trancheAddress] = true;
        deal.totalFaceValue += params.originalFaceValue;

        emit TrancheDeployed(
            params.dealId,
            params.trancheId,
            trancheAddress,
            msg.sender,
            params.originalFaceValue
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONFIGURATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Update the tranche implementation address
     * @dev Only affects newly deployed tranches
     * @param newImplementation New implementation contract address
     */
    function setTrancheImplementation(address newImplementation)
        external
        onlyRole(CONFIG_ROLE)
    {
        if (newImplementation == address(0)) revert ZeroAddress();

        address oldImplementation = trancheImplementation;
        trancheImplementation = newImplementation;

        emit ImplementationUpdated(oldImplementation, newImplementation);
    }

    /**
     * @notice Update the default transfer validator
     * @param newValidator New validator address (can be zero to disable)
     */
    function setDefaultTransferValidator(address newValidator)
        external
        onlyRole(CONFIG_ROLE)
    {
        address oldValidator = defaultTransferValidator;
        defaultTransferValidator = newValidator;

        emit DefaultValidatorUpdated(oldValidator, newValidator);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get all tranches for a deal
     * @param dealId Deal identifier
     * @return Array of tranche addresses
     */
    function getTranchesForDeal(bytes32 dealId)
        external
        view
        returns (address[] memory)
    {
        return tranchesByDeal[dealId];
    }

    /**
     * @notice Get the number of tranches for a deal
     * @param dealId Deal identifier
     * @return Number of tranches
     */
    function getTrancheCountForDeal(bytes32 dealId)
        external
        view
        returns (uint256)
    {
        return tranchesByDeal[dealId].length;
    }

    /**
     * @notice Get total number of deployed tranches
     * @return Total tranche count
     */
    function getTotalTrancheCount() external view returns (uint256) {
        return allTranches.length;
    }

    /**
     * @notice Get total number of registered deals
     * @return Total deal count
     */
    function getTotalDealCount() external view returns (uint256) {
        return allDeals.length;
    }

    /**
     * @notice Get deal information
     * @param dealId Deal identifier
     * @return Deal information struct
     */
    function getDealInfo(bytes32 dealId)
        external
        view
        returns (DealInfo memory)
    {
        return deals[dealId];
    }

    /**
     * @notice Get all deal IDs
     * @return Array of deal IDs
     */
    function getAllDeals() external view returns (bytes32[] memory) {
        return allDeals;
    }

    /**
     * @notice Get all tranche addresses
     * @return Array of tranche addresses
     */
    function getAllTranches() external view returns (address[] memory) {
        return allTranches;
    }

    /**
     * @notice Get comprehensive deal summary
     * @param dealId Deal identifier
     * @return info Deal information
     * @return tranches Array of tranche addresses
     * @return trancheCount Number of tranches
     */
    function getDealSummary(bytes32 dealId)
        external
        view
        returns (
            DealInfo memory info,
            address[] memory tranches,
            uint256 trancheCount
        )
    {
        info = deals[dealId];
        tranches = tranchesByDeal[dealId];
        trancheCount = tranches.length;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // UPGRADE AUTHORIZATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Authorize contract upgrade
     * @param newImplementation New implementation address
     */
    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyRole(UPGRADER_ROLE)
    {
        // Additional validation can be added here
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {AccessControlUpgradeable} from
    "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {UUPSUpgradeable} from
    "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";

/**
 * @title RoleRegistry
 * @notice Centralized role-based access control for the RMBS platform
 * @dev Single source of truth for all platform roles and permissions
 * 
 * Key Features:
 * - Centralized role management across all contracts
 * - Platform-wide roles (Arranger, Investor, Servicer, etc.)
 * - Per-deal role assignments
 * - Investor KYC/AML integration
 * - Role hierarchy and delegation
 * - Comprehensive audit trail
 * 
 * Role Hierarchy:
 * - PLATFORM_ADMIN: Full platform control
 * - DEAL_ADMIN: Per-deal administrative control
 * - ARRANGER: Can create and manage deals
 * - TRUSTEE: Can execute waterfall, update factors
 * - SERVICER: Can submit loan data
 * - INVESTOR: Can hold and trade tokens
 * - AUDITOR: Read-only access to all data
 * 
 * @custom:security-contact security@rmbs.io
 */
contract RoleRegistry is AccessControlUpgradeable, UUPSUpgradeable {
    // ═══════════════════════════════════════════════════════════════════════
    // PLATFORM ROLES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Platform administrator (super admin)
    bytes32 public constant PLATFORM_ADMIN = keccak256("PLATFORM_ADMIN");

    /// @notice Can upgrade contracts
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice Can create and manage deals
    bytes32 public constant ARRANGER_ROLE = keccak256("ARRANGER_ROLE");

    /// @notice Can execute waterfall distributions
    bytes32 public constant TRUSTEE_ROLE = keccak256("TRUSTEE_ROLE");

    /// @notice Can submit loan performance data
    bytes32 public constant SERVICER_ROLE = keccak256("SERVICER_ROLE");

    /// @notice Verified investor (can hold securities)
    bytes32 public constant INVESTOR_ROLE = keccak256("INVESTOR_ROLE");

    /// @notice Can manage compliance rules
    bytes32 public constant COMPLIANCE_OFFICER_ROLE = keccak256("COMPLIANCE_OFFICER_ROLE");

    /// @notice Read-only access for auditing
    bytes32 public constant AUDITOR_ROLE = keccak256("AUDITOR_ROLE");

    /// @notice Can manage investor registry
    bytes32 public constant REGISTRAR_ROLE = keccak256("REGISTRAR_ROLE");

    // ═══════════════════════════════════════════════════════════════════════
    // TYPES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice User registration data
    struct UserInfo {
        address userAddress;
        string name;                    // Organization name
        bytes32[] platformRoles;        // Platform-wide roles
        bool isActive;
        uint256 registrationDate;
        uint256 lastActivityDate;
        string metadataURI;             // IPFS link to extended metadata
    }

    /// @notice Deal-specific role assignment
    struct DealRole {
        bytes32 dealId;
        bytes32 role;
        address assignee;
        uint256 assignedAt;
        uint256 expiresAt;              // 0 = never expires
        address assignedBy;
    }

    /// @notice Investor verification status
    struct InvestorStatus {
        bool isVerified;
        bool isAccredited;
        bytes2 jurisdictionCode;        // ISO 3166-1 alpha-2
        uint256 kycExpirationDate;
        uint256 investorLimit;          // Max investment amount (0 = no limit)
        string verificationProvider;    // E.g., "Onfido", "Jumio"
        bytes32 verificationHash;       // Hash of verification data
    }

    // ═══════════════════════════════════════════════════════════════════════
    // STORAGE
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice User information by address
    mapping(address => UserInfo) public users;

    /// @notice All registered users
    address[] public allUsers;

    /// @notice Deal-specific roles: dealId => role => address[]
    mapping(bytes32 => mapping(bytes32 => address[])) public dealRoleMembers;

    /// @notice Check if address has deal role: dealId => role => address => bool
    mapping(bytes32 => mapping(bytes32 => mapping(address => bool))) public hasDealRole;

    /// @notice Deal role details: dealId => role => address => DealRole
    mapping(bytes32 => mapping(bytes32 => mapping(address => DealRole))) public dealRoleDetails;

    /// @notice Investor verification status
    mapping(address => InvestorStatus) public investorStatus;

    /// @notice Registered contracts that can query roles
    mapping(address => bool) public registeredContracts;

    /// @notice Contract names for registered contracts
    mapping(address => string) public contractNames;

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a user is registered
    event UserRegistered(
        address indexed user,
        string name,
        uint256 timestamp
    );

    /// @notice Emitted when a user is deactivated
    event UserDeactivated(
        address indexed user,
        uint256 timestamp
    );

    /// @notice Emitted when a platform role is granted
    event PlatformRoleGranted(
        address indexed user,
        bytes32 indexed role,
        address indexed grantedBy
    );

    /// @notice Emitted when a platform role is revoked
    event PlatformRoleRevoked(
        address indexed user,
        bytes32 indexed role,
        address indexed revokedBy
    );

    /// @notice Emitted when a deal role is assigned
    event DealRoleAssigned(
        bytes32 indexed dealId,
        bytes32 indexed role,
        address indexed assignee,
        address assignedBy,
        uint256 expiresAt
    );

    /// @notice Emitted when a deal role is revoked
    event DealRoleRevoked(
        bytes32 indexed dealId,
        bytes32 indexed role,
        address indexed assignee,
        address revokedBy
    );

    /// @notice Emitted when investor status is updated
    event InvestorStatusUpdated(
        address indexed investor,
        bool isVerified,
        bool isAccredited,
        bytes2 jurisdictionCode,
        uint256 kycExpiration
    );

    /// @notice Emitted when a contract is registered
    event ContractRegistered(
        address indexed contractAddress,
        string name
    );

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ZeroAddress();
    error UserAlreadyRegistered(address user);
    error UserNotRegistered(address user);
    error UserNotActive(address user);
    error RoleAlreadyAssigned(bytes32 dealId, bytes32 role, address user);
    error RoleNotAssigned(bytes32 dealId, bytes32 role, address user);
    error RoleExpired(bytes32 dealId, bytes32 role, address user);
    error InvalidExpiration(uint256 expiration);
    error NotAuthorized();
    error ContractAlreadyRegistered(address contractAddress);

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZER
    // ═══════════════════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the registry
     * @param admin Platform admin address
     */
    function initialize(address admin) external initializer {
        if (admin == address(0)) revert ZeroAddress();

        __AccessControl_init();
        __UUPSUpgradeable_init();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(PLATFORM_ADMIN, admin);
        _grantRole(UPGRADER_ROLE, admin);

        // Set role admins
        _setRoleAdmin(ARRANGER_ROLE, PLATFORM_ADMIN);
        _setRoleAdmin(TRUSTEE_ROLE, PLATFORM_ADMIN);
        _setRoleAdmin(SERVICER_ROLE, PLATFORM_ADMIN);
        _setRoleAdmin(INVESTOR_ROLE, REGISTRAR_ROLE);
        _setRoleAdmin(COMPLIANCE_OFFICER_ROLE, PLATFORM_ADMIN);
        _setRoleAdmin(AUDITOR_ROLE, PLATFORM_ADMIN);
        _setRoleAdmin(REGISTRAR_ROLE, PLATFORM_ADMIN);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // USER MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Register a new user
     * @param userAddress User's wallet address
     * @param name Organization/individual name
     * @param metadataURI IPFS link to extended metadata
     */
    function registerUser(
        address userAddress,
        string calldata name,
        string calldata metadataURI
    ) external onlyRole(REGISTRAR_ROLE) {
        if (userAddress == address(0)) revert ZeroAddress();
        if (users[userAddress].userAddress != address(0)) {
            revert UserAlreadyRegistered(userAddress);
        }

        users[userAddress] = UserInfo({
            userAddress: userAddress,
            name: name,
            platformRoles: new bytes32[](0),
            isActive: true,
            registrationDate: block.timestamp,
            lastActivityDate: block.timestamp,
            metadataURI: metadataURI
        });

        allUsers.push(userAddress);

        emit UserRegistered(userAddress, name, block.timestamp);
    }

    /**
     * @notice Deactivate a user
     * @param userAddress User's wallet address
     */
    function deactivateUser(address userAddress)
        external
        onlyRole(PLATFORM_ADMIN)
    {
        if (users[userAddress].userAddress == address(0)) {
            revert UserNotRegistered(userAddress);
        }

        users[userAddress].isActive = false;

        emit UserDeactivated(userAddress, block.timestamp);
    }

    /**
     * @notice Reactivate a user
     * @param userAddress User's wallet address
     */
    function reactivateUser(address userAddress)
        external
        onlyRole(PLATFORM_ADMIN)
    {
        if (users[userAddress].userAddress == address(0)) {
            revert UserNotRegistered(userAddress);
        }

        users[userAddress].isActive = true;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // PLATFORM ROLE MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Grant a platform role to a user
     * @param user User address
     * @param role Role to grant
     */
    function grantPlatformRole(address user, bytes32 role)
        external
        onlyRole(getRoleAdmin(role))
    {
        if (!users[user].isActive) revert UserNotActive(user);

        _grantRole(role, user);
        users[user].platformRoles.push(role);

        emit PlatformRoleGranted(user, role, msg.sender);
    }

    /**
     * @notice Revoke a platform role from a user
     * @param user User address
     * @param role Role to revoke
     */
    function revokePlatformRole(address user, bytes32 role)
        external
        onlyRole(getRoleAdmin(role))
    {
        _revokeRole(role, user);

        // Remove from user's role list
        bytes32[] storage roles = users[user].platformRoles;
        for (uint256 i = 0; i < roles.length; i++) {
            if (roles[i] == role) {
                roles[i] = roles[roles.length - 1];
                roles.pop();
                break;
            }
        }

        emit PlatformRoleRevoked(user, role, msg.sender);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL ROLE MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Assign a deal-specific role
     * @param dealId Deal identifier
     * @param role Role to assign
     * @param assignee Address to assign role to
     * @param expiresAt Expiration timestamp (0 = never)
     */
    function assignDealRole(
        bytes32 dealId,
        bytes32 role,
        address assignee,
        uint256 expiresAt
    ) external onlyRole(ARRANGER_ROLE) {
        if (assignee == address(0)) revert ZeroAddress();
        if (hasDealRole[dealId][role][assignee]) {
            revert RoleAlreadyAssigned(dealId, role, assignee);
        }
        if (expiresAt != 0 && expiresAt <= block.timestamp) {
            revert InvalidExpiration(expiresAt);
        }

        hasDealRole[dealId][role][assignee] = true;
        dealRoleMembers[dealId][role].push(assignee);
        dealRoleDetails[dealId][role][assignee] = DealRole({
            dealId: dealId,
            role: role,
            assignee: assignee,
            assignedAt: block.timestamp,
            expiresAt: expiresAt,
            assignedBy: msg.sender
        });

        emit DealRoleAssigned(dealId, role, assignee, msg.sender, expiresAt);
    }

    /**
     * @notice Revoke a deal-specific role
     * @param dealId Deal identifier
     * @param role Role to revoke
     * @param assignee Address to revoke from
     */
    function revokeDealRole(
        bytes32 dealId,
        bytes32 role,
        address assignee
    ) external onlyRole(ARRANGER_ROLE) {
        if (!hasDealRole[dealId][role][assignee]) {
            revert RoleNotAssigned(dealId, role, assignee);
        }

        hasDealRole[dealId][role][assignee] = false;

        // Remove from members list
        address[] storage members = dealRoleMembers[dealId][role];
        for (uint256 i = 0; i < members.length; i++) {
            if (members[i] == assignee) {
                members[i] = members[members.length - 1];
                members.pop();
                break;
            }
        }

        delete dealRoleDetails[dealId][role][assignee];

        emit DealRoleRevoked(dealId, role, assignee, msg.sender);
    }

    /**
     * @notice Check if user has an active deal role
     * @param dealId Deal identifier
     * @param role Role to check
     * @param user User address
     * @return True if user has active role
     */
    function hasActiveDealRole(bytes32 dealId, bytes32 role, address user)
        public
        view
        returns (bool)
    {
        if (!hasDealRole[dealId][role][user]) return false;

        DealRole storage details = dealRoleDetails[dealId][role][user];
        if (details.expiresAt != 0 && details.expiresAt < block.timestamp) {
            return false;
        }

        return true;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INVESTOR STATUS MANAGEMENT
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Update investor verification status
     * @param investor Investor address
     * @param isVerified KYC verified
     * @param isAccredited Accredited investor
     * @param jurisdictionCode ISO country code
     * @param kycExpirationDate KYC expiration
     * @param investorLimit Maximum investment amount
     * @param verificationProvider KYC provider name
     * @param verificationHash Hash of verification data
     */
    function updateInvestorStatus(
        address investor,
        bool isVerified,
        bool isAccredited,
        bytes2 jurisdictionCode,
        uint256 kycExpirationDate,
        uint256 investorLimit,
        string calldata verificationProvider,
        bytes32 verificationHash
    ) external onlyRole(COMPLIANCE_OFFICER_ROLE) {
        investorStatus[investor] = InvestorStatus({
            isVerified: isVerified,
            isAccredited: isAccredited,
            jurisdictionCode: jurisdictionCode,
            kycExpirationDate: kycExpirationDate,
            investorLimit: investorLimit,
            verificationProvider: verificationProvider,
            verificationHash: verificationHash
        });

        // Grant/revoke INVESTOR_ROLE based on verification
        if (isVerified && kycExpirationDate > block.timestamp) {
            if (!hasRole(INVESTOR_ROLE, investor)) {
                _grantRole(INVESTOR_ROLE, investor);
            }
        } else {
            if (hasRole(INVESTOR_ROLE, investor)) {
                _revokeRole(INVESTOR_ROLE, investor);
            }
        }

        emit InvestorStatusUpdated(
            investor,
            isVerified,
            isAccredited,
            jurisdictionCode,
            kycExpirationDate
        );
    }

    /**
     * @notice Check if investor is verified and not expired
     * @param investor Investor address
     * @return True if verified and KYC not expired
     */
    function isInvestorVerified(address investor) public view returns (bool) {
        InvestorStatus storage status = investorStatus[investor];
        return status.isVerified && status.kycExpirationDate > block.timestamp;
    }

    /**
     * @notice Check if investor is accredited
     * @param investor Investor address
     * @return True if accredited
     */
    function isInvestorAccredited(address investor) public view returns (bool) {
        return investorStatus[investor].isAccredited && isInvestorVerified(investor);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONTRACT REGISTRATION
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Register a contract to query roles
     * @param contractAddress Contract address
     * @param name Contract name
     */
    function registerContract(address contractAddress, string calldata name)
        external
        onlyRole(PLATFORM_ADMIN)
    {
        if (contractAddress == address(0)) revert ZeroAddress();
        if (registeredContracts[contractAddress]) {
            revert ContractAlreadyRegistered(contractAddress);
        }

        registeredContracts[contractAddress] = true;
        contractNames[contractAddress] = name;

        emit ContractRegistered(contractAddress, name);
    }

    /**
     * @notice Unregister a contract
     * @param contractAddress Contract address
     */
    function unregisterContract(address contractAddress)
        external
        onlyRole(PLATFORM_ADMIN)
    {
        registeredContracts[contractAddress] = false;
        delete contractNames[contractAddress];
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get user information
     * @param user User address
     * @return User info struct
     */
    function getUserInfo(address user)
        external
        view
        returns (UserInfo memory)
    {
        return users[user];
    }

    /**
     * @notice Get all platform roles for a user
     * @param user User address
     * @return Array of role identifiers
     */
    function getUserPlatformRoles(address user)
        external
        view
        returns (bytes32[] memory)
    {
        return users[user].platformRoles;
    }

    /**
     * @notice Get all members of a deal role
     * @param dealId Deal identifier
     * @param role Role to query
     * @return Array of addresses with the role
     */
    function getDealRoleMembers(bytes32 dealId, bytes32 role)
        external
        view
        returns (address[] memory)
    {
        return dealRoleMembers[dealId][role];
    }

    /**
     * @notice Get investor status
     * @param investor Investor address
     * @return Investor status struct
     */
    function getInvestorStatus(address investor)
        external
        view
        returns (InvestorStatus memory)
    {
        return investorStatus[investor];
    }

    /**
     * @notice Get total registered users
     * @return Count of all users
     */
    function getTotalUsers() external view returns (uint256) {
        return allUsers.length;
    }

    /**
     * @notice Get all registered users
     * @return Array of user addresses
     */
    function getAllUsers() external view returns (address[] memory) {
        return allUsers;
    }

    /**
     * @notice Check if a user can act as a specific role for a deal
     * @param user User address
     * @param dealId Deal identifier
     * @param role Role to check
     * @return True if user has either platform role or active deal role
     */
    function canActAs(address user, bytes32 dealId, bytes32 role)
        external
        view
        returns (bool)
    {
        // Check platform-wide role first
        if (hasRole(role, user)) return true;

        // Check deal-specific role
        return hasActiveDealRole(dealId, role, user);
    }

    /**
     * @notice Batch check roles for multiple users
     * @param usersToCheck Array of user addresses
     * @param role Role to check
     * @return Array of booleans indicating role membership
     */
    function batchCheckRole(address[] calldata usersToCheck, bytes32 role)
        external
        view
        returns (bool[] memory)
    {
        bool[] memory results = new bool[](usersToCheck.length);
        for (uint256 i = 0; i < usersToCheck.length; i++) {
            results[i] = hasRole(role, usersToCheck[i]);
        }
        return results;
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

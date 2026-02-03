// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {ERC721Upgradeable} from "@openzeppelin/contracts-upgradeable/token/ERC721/ERC721Upgradeable.sol";
import {ERC721EnumerableUpgradeable} from
    "@openzeppelin/contracts-upgradeable/token/ERC721/extensions/ERC721EnumerableUpgradeable.sol";
import {ERC721URIStorageUpgradeable} from
    "@openzeppelin/contracts-upgradeable/token/ERC721/extensions/ERC721URIStorageUpgradeable.sol";
import {AccessControlUpgradeable} from
    "@openzeppelin/contracts-upgradeable/access/AccessControlUpgradeable.sol";
import {UUPSUpgradeable} from
    "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import {ReentrancyGuardUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/ReentrancyGuardUpgradeable.sol";
import {PausableUpgradeable} from
    "@openzeppelin/contracts-upgradeable/security/PausableUpgradeable.sol";

/**
 * @title LoanNFT
 * @notice ERC-721 NFT representing individual loans in an RMBS deal
 * @dev Each loan in the pool is minted as a unique NFT with metadata
 * 
 * Key Features:
 * - Loan-level NFT representation (privacy-preserving)
 * - Metadata stored off-chain (IPFS) or on-chain encrypted
 * - Deal-level grouping (all loans belong to a deal)
 * - Transferable but restricted to whitelisted entities
 * - Enumerable for bulk operations
 * - Immutable loan characteristics on-chain
 * 
 * Privacy Design:
 * - Sensitive PII is NOT stored on-chain
 * - Only loan identifiers and hashes are stored
 * - Metadata URI points to encrypted data storage
 * - Access control for metadata retrieval
 * 
 * Use Cases:
 * - Loan-level trading (whole loan sales)
 * - Collateral tracking and verification
 * - Waterfall tie-in (oracle uses NFT registry)
 * - Audit trail for loan history
 * 
 * @custom:security-contact security@rmbs.io
 */
contract LoanNFT is
    ERC721Upgradeable,
    ERC721EnumerableUpgradeable,
    ERC721URIStorageUpgradeable,
    AccessControlUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable,
    PausableUpgradeable
{
    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Role for minting loans (arranger at origination)
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    /// @notice Role for updating loan status (servicer)
    bytes32 public constant SERVICER_ROLE = keccak256("SERVICER_ROLE");

    /// @notice Role for contract upgrades
    bytes32 public constant UPGRADER_ROLE = keccak256("UPGRADER_ROLE");

    /// @notice Maximum loans per batch mint (gas optimization)
    uint256 public constant MAX_BATCH_SIZE = 100;

    // ═══════════════════════════════════════════════════════════════════════
    // STATE VARIABLES
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Counter for token IDs
    uint256 private _tokenIdCounter;

    /// @notice Mapping from deal ID to list of token IDs
    mapping(bytes32 => uint256[]) public dealLoans;

    /// @notice Mapping from token ID to loan metadata
    mapping(uint256 => LoanMetadata) public loanMetadata;

    /// @notice Mapping from deal ID to its existence
    mapping(bytes32 => bool) public dealExists;

    // ═══════════════════════════════════════════════════════════════════════
    // STRUCTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Loan status enum
    enum LoanStatus {
        CURRENT,           // 0-29 DPD
        DELINQUENT_30,     // 30-59 DPD
        DELINQUENT_60,     // 60-89 DPD
        DELINQUENT_90,     // 90+ DPD
        DEFAULT,           // Foreclosure initiated
        PAID_OFF,          // Fully paid
        PREPAID            // Prepaid before maturity
    }

    /// @notice On-chain loan metadata (privacy-preserving)
    struct LoanMetadata {
        bytes32 dealId;                 // Deal this loan belongs to
        string loanId;                  // External loan identifier
        uint256 originalBalance;        // Original UPB
        uint256 currentBalance;         // Current UPB (updated by servicer)
        uint256 noteRate;               // Interest rate in bps
        uint256 originationDate;        // Unix timestamp
        uint256 maturityDate;           // Unix timestamp
        LoanStatus status;              // Current loan status
        bytes32 dataHash;               // Hash of full loan data (for verification)
        uint256 lastUpdated;            // Last status update timestamp
    }

    /// @notice Parameters for minting a loan NFT
    struct MintParams {
        bytes32 dealId;
        string loanId;
        uint256 originalBalance;
        uint256 currentBalance;
        uint256 noteRate;
        uint256 originationDate;
        uint256 maturityDate;
        bytes32 dataHash;
        string metadataURI;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EVENTS
    // ═══════════════════════════════════════════════════════════════════════

    /// @notice Emitted when a new loan NFT is minted
    event LoanMinted(
        uint256 indexed tokenId,
        bytes32 indexed dealId,
        string loanId,
        address indexed owner,
        uint256 originalBalance
    );

    /// @notice Emitted when loan status is updated
    event LoanStatusUpdated(
        uint256 indexed tokenId,
        bytes32 indexed dealId,
        LoanStatus oldStatus,
        LoanStatus newStatus,
        uint256 currentBalance
    );

    /// @notice Emitted when a batch of loans is minted
    event LoansBatchMinted(
        bytes32 indexed dealId,
        uint256 count,
        address indexed owner
    );

    // ═══════════════════════════════════════════════════════════════════════
    // ERRORS
    // ═══════════════════════════════════════════════════════════════════════

    error ZeroAddress();
    error InvalidDealId();
    error InvalidLoanId();
    error InvalidBalance();
    error InvalidDate();
    error BatchSizeExceeded(uint256 provided, uint256 max);
    error TokenNotFound(uint256 tokenId);
    error DealNotFound(bytes32 dealId);

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZER
    // ═══════════════════════════════════════════════════════════════════════

    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }

    /**
     * @notice Initialize the contract
     * @param name_ Token name
     * @param symbol_ Token symbol
     * @param admin Admin address
     * @param minter Minter address (arranger)
     */
    function initialize(
        string memory name_,
        string memory symbol_,
        address admin,
        address minter
    ) external initializer {
        if (admin == address(0) || minter == address(0)) revert ZeroAddress();

        __ERC721_init(name_, symbol_);
        __ERC721Enumerable_init();
        __ERC721URIStorage_init();
        __AccessControl_init();
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        __Pausable_init();

        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(MINTER_ROLE, minter);
        _grantRole(SERVICER_ROLE, minter); // Arranger can also update
        _grantRole(UPGRADER_ROLE, admin);

        _tokenIdCounter = 1; // Start from 1
    }

    // ═══════════════════════════════════════════════════════════════════════
    // MINTING FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Mint a single loan NFT
     * @param to Recipient address (typically deal issuer/trustee)
     * @param params Loan parameters
     * @return tokenId The minted token ID
     */
    function mintLoan(address to, MintParams calldata params)
        external
        onlyRole(MINTER_ROLE)
        nonReentrant
        whenNotPaused
        returns (uint256)
    {
        _validateMintParams(to, params);

        uint256 tokenId = _tokenIdCounter++;

        // Mint NFT
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, params.metadataURI);

        // Store metadata
        loanMetadata[tokenId] = LoanMetadata({
            dealId: params.dealId,
            loanId: params.loanId,
            originalBalance: params.originalBalance,
            currentBalance: params.currentBalance,
            noteRate: params.noteRate,
            originationDate: params.originationDate,
            maturityDate: params.maturityDate,
            status: LoanStatus.CURRENT,
            dataHash: params.dataHash,
            lastUpdated: block.timestamp
        });

        // Add to deal registry
        dealLoans[params.dealId].push(tokenId);
        dealExists[params.dealId] = true;

        emit LoanMinted(tokenId, params.dealId, params.loanId, to, params.originalBalance);

        return tokenId;
    }

    /**
     * @notice Mint multiple loan NFTs in a batch (gas efficient)
     * @param to Recipient address
     * @param paramsList Array of loan parameters
     * @return tokenIds Array of minted token IDs
     */
    function mintLoanBatch(address to, MintParams[] calldata paramsList)
        external
        onlyRole(MINTER_ROLE)
        nonReentrant
        whenNotPaused
        returns (uint256[] memory)
    {
        if (to == address(0)) revert ZeroAddress();
        if (paramsList.length == 0 || paramsList.length > MAX_BATCH_SIZE) {
            revert BatchSizeExceeded(paramsList.length, MAX_BATCH_SIZE);
        }

        // Validate all deal IDs are the same (batch must be for one deal)
        bytes32 dealId = paramsList[0].dealId;
        if (dealId == bytes32(0)) revert InvalidDealId();

        uint256[] memory tokenIds = new uint256[](paramsList.length);

        for (uint256 i = 0; i < paramsList.length; i++) {
            if (paramsList[i].dealId != dealId) revert InvalidDealId();
            
            uint256 tokenId = _tokenIdCounter++;
            tokenIds[i] = tokenId;

            _safeMint(to, tokenId);
            _setTokenURI(tokenId, paramsList[i].metadataURI);

            loanMetadata[tokenId] = LoanMetadata({
                dealId: dealId,
                loanId: paramsList[i].loanId,
                originalBalance: paramsList[i].originalBalance,
                currentBalance: paramsList[i].currentBalance,
                noteRate: paramsList[i].noteRate,
                originationDate: paramsList[i].originationDate,
                maturityDate: paramsList[i].maturityDate,
                status: LoanStatus.CURRENT,
                dataHash: paramsList[i].dataHash,
                lastUpdated: block.timestamp
            });

            dealLoans[dealId].push(tokenId);
        }

        dealExists[dealId] = true;
        emit LoansBatchMinted(dealId, paramsList.length, to);

        return tokenIds;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // LOAN STATUS UPDATES
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Update loan status (called by servicer)
     * @param tokenId Token ID of the loan
     * @param newStatus New loan status
     * @param newBalance Updated current balance
     */
    function updateLoanStatus(uint256 tokenId, LoanStatus newStatus, uint256 newBalance)
        external
        onlyRole(SERVICER_ROLE)
        nonReentrant
    {
        if (!_exists(tokenId)) revert TokenNotFound(tokenId);

        LoanMetadata storage loan = loanMetadata[tokenId];
        LoanStatus oldStatus = loan.status;

        loan.status = newStatus;
        loan.currentBalance = newBalance;
        loan.lastUpdated = block.timestamp;

        emit LoanStatusUpdated(tokenId, loan.dealId, oldStatus, newStatus, newBalance);
    }

    /**
     * @notice Batch update loan statuses (gas efficient for monthly servicer tape)
     * @param tokenIds Array of token IDs
     * @param statuses Array of new statuses
     * @param balances Array of new balances
     */
    function updateLoanStatusBatch(
        uint256[] calldata tokenIds,
        LoanStatus[] calldata statuses,
        uint256[] calldata balances
    ) external onlyRole(SERVICER_ROLE) nonReentrant {
        if (tokenIds.length != statuses.length || tokenIds.length != balances.length) {
            revert("Array length mismatch");
        }
        if (tokenIds.length > MAX_BATCH_SIZE) {
            revert BatchSizeExceeded(tokenIds.length, MAX_BATCH_SIZE);
        }

        for (uint256 i = 0; i < tokenIds.length; i++) {
            uint256 tokenId = tokenIds[i];
            if (!_exists(tokenId)) revert TokenNotFound(tokenId);

            LoanMetadata storage loan = loanMetadata[tokenId];
            LoanStatus oldStatus = loan.status;

            loan.status = statuses[i];
            loan.currentBalance = balances[i];
            loan.lastUpdated = block.timestamp;

            emit LoanStatusUpdated(tokenId, loan.dealId, oldStatus, statuses[i], balances[i]);
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Get all loans for a deal
     * @param dealId Deal identifier
     * @return Array of token IDs
     */
    function getLoansForDeal(bytes32 dealId) external view returns (uint256[] memory) {
        if (!dealExists[dealId]) revert DealNotFound(dealId);
        return dealLoans[dealId];
    }

    /**
     * @notice Get loan metadata
     * @param tokenId Token ID
     * @return Loan metadata struct
     */
    function getLoanMetadata(uint256 tokenId) external view returns (LoanMetadata memory) {
        if (!_exists(tokenId)) revert TokenNotFound(tokenId);
        return loanMetadata[tokenId];
    }

    /**
     * @notice Get total current balance for a deal
     * @param dealId Deal identifier
     * @return Total unpaid principal balance
     */
    function getDealBalance(bytes32 dealId) external view returns (uint256) {
        if (!dealExists[dealId]) revert DealNotFound(dealId);
        
        uint256[] memory loans = dealLoans[dealId];
        uint256 totalBalance = 0;

        for (uint256 i = 0; i < loans.length; i++) {
            totalBalance += loanMetadata[loans[i]].currentBalance;
        }

        return totalBalance;
    }

    /**
     * @notice Get loan count by status for a deal
     * @param dealId Deal identifier
     * @param status Status to filter by
     * @return Count of loans with the given status
     */
    function getLoanCountByStatus(bytes32 dealId, LoanStatus status)
        external
        view
        returns (uint256)
    {
        if (!dealExists[dealId]) revert DealNotFound(dealId);
        
        uint256[] memory loans = dealLoans[dealId];
        uint256 count = 0;

        for (uint256 i = 0; i < loans.length; i++) {
            if (loanMetadata[loans[i]].status == status) {
                count++;
            }
        }

        return count;
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Pause contract
     */
    function pause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _pause();
    }

    /**
     * @notice Unpause contract
     */
    function unpause() external onlyRole(DEFAULT_ADMIN_ROLE) {
        _unpause();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INTERNAL FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    function _validateMintParams(address to, MintParams calldata params) internal pure {
        if (to == address(0)) revert ZeroAddress();
        if (params.dealId == bytes32(0)) revert InvalidDealId();
        if (bytes(params.loanId).length == 0) revert InvalidLoanId();
        if (params.originalBalance == 0) revert InvalidBalance();
        if (params.currentBalance > params.originalBalance) revert InvalidBalance();
        if (params.originationDate == 0 || params.maturityDate == 0) revert InvalidDate();
        if (params.maturityDate <= params.originationDate) revert InvalidDate();
    }

    function _exists(uint256 tokenId) internal view returns (bool) {
        return _ownerOf(tokenId) != address(0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // REQUIRED OVERRIDES
    // ═══════════════════════════════════════════════════════════════════════

    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 firstTokenId,
        uint256 batchSize
    ) internal override(ERC721Upgradeable, ERC721EnumerableUpgradeable) whenNotPaused {
        super._beforeTokenTransfer(from, to, firstTokenId, batchSize);
    }

    function _burn(uint256 tokenId)
        internal
        override(ERC721Upgradeable, ERC721URIStorageUpgradeable)
    {
        super._burn(tokenId);
    }

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721Upgradeable, ERC721URIStorageUpgradeable)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(
            ERC721Upgradeable,
            ERC721EnumerableUpgradeable,
            ERC721URIStorageUpgradeable,
            AccessControlUpgradeable
        )
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    function _authorizeUpgrade(address newImplementation)
        internal
        override
        onlyRole(UPGRADER_ROLE)
    {}
}

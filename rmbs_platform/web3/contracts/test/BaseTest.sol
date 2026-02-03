// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

// Mock ERC20 for testing
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @title BaseTest
 * @notice Base test contract with common utilities and setup
 */
abstract contract BaseTest is Test {
    // ═══════════════════════════════════════════════════════════════════════
    // TEST ACCOUNTS
    // ═══════════════════════════════════════════════════════════════════════

    address public admin;
    address public arranger;
    address public trustee;
    address public servicer;
    address public complianceOfficer;
    address public investor1;
    address public investor2;
    address public investor3;
    address public auditor;
    address public attacker;

    // ═══════════════════════════════════════════════════════════════════════
    // CONSTANTS
    // ═══════════════════════════════════════════════════════════════════════

    bytes32 public constant DEAL_ID_1 = keccak256("DEAL_2024_001");
    bytes32 public constant DEAL_ID_2 = keccak256("DEAL_2024_002");
    
    string public constant TRANCHE_A = "A1";
    string public constant TRANCHE_M = "M1";
    string public constant TRANCHE_B = "B1";

    uint256 public constant INITIAL_BALANCE = 1_000_000e6; // 1M USDC
    uint256 public constant TRANCHE_FACE_VALUE = 10_000_000e6; // 10M USDC
    
    // ═══════════════════════════════════════════════════════════════════════
    // SETUP
    // ═══════════════════════════════════════════════════════════════════════

    function setUp() public virtual {
        // Create test accounts with labels
        admin = makeAddr("admin");
        arranger = makeAddr("arranger");
        trustee = makeAddr("trustee");
        servicer = makeAddr("servicer");
        complianceOfficer = makeAddr("complianceOfficer");
        investor1 = makeAddr("investor1");
        investor2 = makeAddr("investor2");
        investor3 = makeAddr("investor3");
        auditor = makeAddr("auditor");
        attacker = makeAddr("attacker");

        // Label accounts for better trace output
        vm.label(admin, "Admin");
        vm.label(arranger, "Arranger");
        vm.label(trustee, "Trustee");
        vm.label(servicer, "Servicer");
        vm.label(complianceOfficer, "ComplianceOfficer");
        vm.label(investor1, "Investor1");
        vm.label(investor2, "Investor2");
        vm.label(investor3, "Investor3");
        vm.label(auditor, "Auditor");
        vm.label(attacker, "Attacker");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════════════════════════════════

    /**
     * @notice Deploy a contract behind a UUPS proxy
     * @param implementation Implementation address
     * @param initData Initialization data
     * @return proxy Proxy address
     */
    function deployProxy(address implementation, bytes memory initData)
        internal
        returns (address proxy)
    {
        proxy = address(new ERC1967Proxy(implementation, initData));
    }

    // NOTE: Removed helper functions that conflict with forge-std:
    // - skip() - use inherited from StdCheats
    // - makeAccount() - use makeAddr() from StdCheats
    // - bound() - already inherited from StdCheats
}

/**
 * @title MockUSDC
 * @notice Mock USDC token for testing
 */
contract MockUSDC is ERC20 {
    constructor() ERC20("USD Coin", "USDC") {}

    function decimals() public pure override returns (uint8) {
        return 6;
    }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external {
        _burn(from, amount);
    }
}

/**
 * @title MockFailingTransferValidator
 * @notice Mock validator that always fails (for testing)
 */
contract MockFailingTransferValidator {
    bytes32 public constant TRANSFER_FAILURE = bytes32(uint256(0x50)); // ESC_50 = transfer failure

    function canTransfer(
        bytes32,
        address,
        address,
        uint256,
        bytes calldata
    ) external pure returns (bytes32) {
        return TRANSFER_FAILURE;
    }
}

/**
 * @title MockPassingTransferValidator
 * @notice Mock validator that always passes (for testing)
 */
contract MockPassingTransferValidator {
    bytes32 public constant TRANSFER_SUCCESS = bytes32(uint256(0x51)); // ESC_51 = success

    function canTransfer(
        bytes32,
        address,
        address,
        uint256,
        bytes calldata
    ) external pure returns (bytes32) {
        return TRANSFER_SUCCESS;
    }
}

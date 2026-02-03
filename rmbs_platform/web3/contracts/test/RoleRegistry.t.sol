// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest} from "./BaseTest.sol";
import {RoleRegistry} from "../src/access/RoleRegistry.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title RoleRegistryTest
 * @notice Unit tests for RoleRegistry contract
 */
contract RoleRegistryTest is BaseTest {
    RoleRegistry public registry;
    RoleRegistry public registryImpl;

    bytes32 constant TEST_DEAL_ID = keccak256("DEAL_2024_TEST");
    bytes32 constant ARRANGER_ROLE = keccak256("ARRANGER_ROLE");
    bytes32 constant TRUSTEE_ROLE = keccak256("TRUSTEE_ROLE");
    bytes32 constant SERVICER_ROLE = keccak256("SERVICER_ROLE");
    bytes32 constant INVESTOR_ROLE = keccak256("INVESTOR_ROLE");

    event PlatformRoleGranted(
        bytes32 indexed role,
        address indexed account,
        uint64 expiresAt
    );

    event PlatformRoleRevoked(
        bytes32 indexed role,
        address indexed account
    );

    event DealRoleGranted(
        bytes32 indexed dealId,
        bytes32 indexed role,
        address indexed account,
        uint64 expiresAt
    );

    event DealRoleRevoked(
        bytes32 indexed dealId,
        bytes32 indexed role,
        address indexed account
    );

    function setUp() public override {
        super.setUp();

        // Deploy RoleRegistry
        registryImpl = new RoleRegistry();
        bytes memory registryInitData = abi.encodeWithSelector(
            RoleRegistry.initialize.selector,
            admin
        );
        address registryProxy = address(new ERC1967Proxy(address(registryImpl), registryInitData));
        registry = RoleRegistry(registryProxy);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertTrue(registry.hasRole(registry.DEFAULT_ADMIN_ROLE(), admin));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // PLATFORM ROLE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_grantPlatformRole_success() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        vm.expectEmit(true, true, false, true);
        emit PlatformRoleGranted(TRUSTEE_ROLE, trustee, expiresAt);
        
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, expiresAt);

        assertTrue(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
    }

    function test_grantPlatformRole_revert_notAdmin() public {
        vm.prank(investor1);
        vm.expectRevert();
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, uint64(block.timestamp + 365 days));
    }

    function test_grantPlatformRole_revert_pastExpiry() public {
        vm.prank(admin);
        vm.expectRevert();
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, uint64(block.timestamp - 1));
    }

    function test_revokePlatformRole_success() public {
        vm.startPrank(admin);
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, uint64(block.timestamp + 365 days));
        
        vm.expectEmit(true, true, false, true);
        emit PlatformRoleRevoked(TRUSTEE_ROLE, trustee);
        
        registry.revokePlatformRole(TRUSTEE_ROLE, trustee);
        vm.stopPrank();

        assertFalse(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
    }

    function test_hasPlatformRole_expired() public {
        uint64 expiresAt = uint64(block.timestamp + 1);

        vm.prank(admin);
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, expiresAt);

        assertTrue(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));

        // Warp time past expiry
        vm.warp(block.timestamp + 2);

        assertFalse(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL ROLE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_grantDealRole_success() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        vm.expectEmit(true, true, true, true);
        emit DealRoleGranted(TEST_DEAL_ID, ARRANGER_ROLE, arranger, expiresAt);
        
        registry.grantDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger, expiresAt);

        assertTrue(registry.hasDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger));
    }

    function test_grantDealRole_revert_notAdmin() public {
        vm.prank(investor1);
        vm.expectRevert();
        registry.grantDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger, uint64(block.timestamp + 365 days));
    }

    function test_revokeDealRole_success() public {
        vm.startPrank(admin);
        registry.grantDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger, uint64(block.timestamp + 365 days));
        
        vm.expectEmit(true, true, true, true);
        emit DealRoleRevoked(TEST_DEAL_ID, ARRANGER_ROLE, arranger);
        
        registry.revokeDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger);
        vm.stopPrank();

        assertFalse(registry.hasDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger));
    }

    function test_hasDealRole_expired() public {
        uint64 expiresAt = uint64(block.timestamp + 1);

        vm.prank(admin);
        registry.grantDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger, expiresAt);

        assertTrue(registry.hasDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger));

        // Warp time past expiry
        vm.warp(block.timestamp + 2);

        assertFalse(registry.hasDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BATCH OPERATIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_batchGrantPlatformRole_success() public {
        address[] memory accounts = new address[](3);
        accounts[0] = investor1;
        accounts[1] = investor2;
        accounts[2] = investor3;

        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        registry.batchGrantPlatformRole(INVESTOR_ROLE, accounts, expiresAt);

        assertTrue(registry.hasPlatformRole(INVESTOR_ROLE, investor1));
        assertTrue(registry.hasPlatformRole(INVESTOR_ROLE, investor2));
        assertTrue(registry.hasPlatformRole(INVESTOR_ROLE, investor3));
    }

    function test_batchRevokePlatformRole_success() public {
        address[] memory accounts = new address[](3);
        accounts[0] = investor1;
        accounts[1] = investor2;
        accounts[2] = investor3;

        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.startPrank(admin);
        registry.batchGrantPlatformRole(INVESTOR_ROLE, accounts, expiresAt);
        registry.batchRevokePlatformRole(INVESTOR_ROLE, accounts);
        vm.stopPrank();

        assertFalse(registry.hasPlatformRole(INVESTOR_ROLE, investor1));
        assertFalse(registry.hasPlatformRole(INVESTOR_ROLE, investor2));
        assertFalse(registry.hasPlatformRole(INVESTOR_ROLE, investor3));
    }

    function test_batchGrantDealRole_success() public {
        address[] memory accounts = new address[](2);
        accounts[0] = trustee;
        accounts[1] = servicer;

        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        registry.batchGrantDealRole(TEST_DEAL_ID, TRUSTEE_ROLE, accounts, expiresAt);

        assertTrue(registry.hasDealRole(TEST_DEAL_ID, TRUSTEE_ROLE, trustee));
        assertTrue(registry.hasDealRole(TEST_DEAL_ID, TRUSTEE_ROLE, servicer));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getPlatformRoleInfo() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, expiresAt);

        (bool hasRole, uint64 returnedExpiry) = registry.getPlatformRoleInfo(TRUSTEE_ROLE, trustee);
        
        assertTrue(hasRole);
        assertEq(returnedExpiry, expiresAt);
    }

    function test_getDealRoleInfo() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.prank(admin);
        registry.grantDealRole(TEST_DEAL_ID, ARRANGER_ROLE, arranger, expiresAt);

        (bool hasRole, uint64 returnedExpiry) = registry.getDealRoleInfo(TEST_DEAL_ID, ARRANGER_ROLE, arranger);
        
        assertTrue(hasRole);
        assertEq(returnedExpiry, expiresAt);
    }

    function test_getAllAccountsWithPlatformRole() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.startPrank(admin);
        registry.grantPlatformRole(INVESTOR_ROLE, investor1, expiresAt);
        registry.grantPlatformRole(INVESTOR_ROLE, investor2, expiresAt);
        registry.grantPlatformRole(INVESTOR_ROLE, investor3, expiresAt);
        vm.stopPrank();

        address[] memory accounts = registry.getAllAccountsWithPlatformRole(INVESTOR_ROLE);
        
        assertEq(accounts.length, 3);
    }

    function test_getAllAccountsWithDealRole() public {
        uint64 expiresAt = uint64(block.timestamp + 365 days);

        vm.startPrank(admin);
        registry.grantDealRole(TEST_DEAL_ID, TRUSTEE_ROLE, trustee, expiresAt);
        registry.grantDealRole(TEST_DEAL_ID, TRUSTEE_ROLE, servicer, expiresAt);
        vm.stopPrank();

        address[] memory accounts = registry.getAllAccountsWithDealRole(TEST_DEAL_ID, TRUSTEE_ROLE);
        
        assertEq(accounts.length, 2);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EMERGENCY TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_pause_unpause() public {
        vm.startPrank(admin);
        registry.pause();
        assertTrue(registry.paused());

        registry.unpause();
        assertFalse(registry.paused());
        vm.stopPrank();
    }

    function test_grantPlatformRole_revert_paused() public {
        vm.prank(admin);
        registry.pause();

        vm.prank(admin);
        vm.expectRevert();
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, uint64(block.timestamp + 365 days));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EDGE CASES
    // ═══════════════════════════════════════════════════════════════════════

    function test_grantRole_withMaxExpiry() public {
        uint64 maxExpiry = type(uint64).max;

        vm.prank(admin);
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, maxExpiry);

        assertTrue(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
        
        // Warp to far future (still should be valid)
        vm.warp(block.timestamp + 100 * 365 days);
        assertTrue(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
    }

    function test_revokeNonExistentRole() public {
        vm.prank(admin);
        // Should not revert, just no-op
        registry.revokePlatformRole(TRUSTEE_ROLE, trustee);

        assertFalse(registry.hasPlatformRole(TRUSTEE_ROLE, trustee));
    }

    function test_grantSameRoleTwice_updatesExpiry() public {
        uint64 firstExpiry = uint64(block.timestamp + 365 days);
        uint64 secondExpiry = uint64(block.timestamp + 730 days);

        vm.startPrank(admin);
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, firstExpiry);
        
        // Grant again with different expiry
        registry.grantPlatformRole(TRUSTEE_ROLE, trustee, secondExpiry);
        vm.stopPrank();

        (, uint64 returnedExpiry) = registry.getPlatformRoleInfo(TRUSTEE_ROLE, trustee);
        assertEq(returnedExpiry, secondExpiry);
    }
}

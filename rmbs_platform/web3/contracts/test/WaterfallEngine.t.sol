// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest} from "./BaseTest.sol";
import {WaterfallEngine} from "../src/waterfall/WaterfallEngine.sol";
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {ServicerOracle} from "../src/oracle/ServicerOracle.sol";
import {RoleRegistry} from "../src/access/RoleRegistry.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title WaterfallEngineTest
 * @notice Unit tests for WaterfallEngine contract
 */
contract WaterfallEngineTest is BaseTest {
    WaterfallEngine public waterfall;
    WaterfallEngine public waterfallImpl;
    ServicerOracle public oracle;
    ServicerOracle public oracleImpl;
    RoleRegistry public roleRegistry;
    RoleRegistry public roleRegistryImpl;
    TransferValidator public validator;
    TransferValidator public validatorImpl;
    
    RMBSTranche public seniorTranche;
    RMBSTranche public mezzTranche;
    RMBSTranche public juniorTranche;
    RMBSTranche public trancheImpl;

    bytes32 constant TEST_DEAL_ID = keccak256("DEAL_2024_TEST");
    
    event WaterfallInitialized(
        bytes32 indexed dealId,
        address indexed paymentToken,
        WaterfallEngine.PrincipalPaydownStrategy strategy
    );

    event DistributionRun(
        bytes32 indexed dealId,
        uint256 period,
        uint256 totalAvailableCash,
        uint256 distributedInterest,
        uint256 distributedPrincipal,
        uint256 remainingCash
    );

    function setUp() public override {
        super.setUp();

        // Deploy RoleRegistry
        roleRegistryImpl = new RoleRegistry();
        bytes memory roleRegistryInitData = abi.encodeWithSelector(
            RoleRegistry.initialize.selector,
            admin
        );
        address roleRegistryProxy = address(new ERC1967Proxy(address(roleRegistryImpl), roleRegistryInitData));
        roleRegistry = RoleRegistry(roleRegistryProxy);

        // Deploy ServicerOracle
        oracleImpl = new ServicerOracle();
        bytes memory oracleInitData = abi.encodeWithSelector(
            ServicerOracle.initialize.selector,
            admin,
            address(roleRegistry)
        );
        address oracleProxy = address(new ERC1967Proxy(address(oracleImpl), oracleInitData));
        oracle = ServicerOracle(oracleProxy);

        // Deploy WaterfallEngine
        waterfallImpl = new WaterfallEngine();
        bytes memory waterfallInitData = abi.encodeWithSelector(
            WaterfallEngine.initialize.selector,
            admin,
            address(roleRegistry),
            address(oracle)
        );
        address waterfallProxy = address(new ERC1967Proxy(address(waterfallImpl), waterfallInitData));
        waterfall = WaterfallEngine(waterfallProxy);

        // Deploy TransferValidator
        validatorImpl = new TransferValidator();
        bytes memory validatorInitData = abi.encodeWithSelector(
            TransferValidator.initialize.selector,
            admin,
            complianceOfficer
        );
        address validatorProxy = address(new ERC1967Proxy(address(validatorImpl), validatorInitData));
        validator = TransferValidator(validatorProxy);

        // Deploy tranche implementation
        trancheImpl = new RMBSTranche();

        // Deploy 3 tranches
        seniorTranche = _deployTranche("SENIOR", "TRMBS-A", 70_000_000e18, 400);
        mezzTranche = _deployTranche("MEZZ", "TRMBS-M", 20_000_000e18, 600);
        juniorTranche = _deployTranche("JUNIOR", "TRMBS-B", 10_000_000e18, 900);

        // Setup roles
        vm.startPrank(admin);
        waterfall.grantRole(waterfall.TRUSTEE_ROLE(), trustee);
        oracle.grantRole(oracle.SERVICER_ROLE(), servicer);
        roleRegistry.grantDealRole(TEST_DEAL_ID, waterfall.TRUSTEE_ROLE(), trustee, type(uint64).max);
        roleRegistry.grantDealRole(TEST_DEAL_ID, keccak256("SERVICER_ROLE"), servicer, type(uint64).max);
        validator.grantRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);
        vm.stopPrank();

        // Setup compliance
        vm.startPrank(complianceOfficer);
        validator.configureDeal(TEST_DEAL_ID, true, false, 0, 0);
        validator.setJurisdictionAllowed(TEST_DEAL_ID, "US", true);
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertEq(address(waterfall.roleRegistry()), address(roleRegistry));
        assertEq(address(waterfall.servicerOracle()), address(oracle));
        assertTrue(waterfall.hasRole(waterfall.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(waterfall.hasRole(waterfall.TRUSTEE_ROLE(), trustee));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // WATERFALL INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initializeDealWaterfall_success() public {
        address[] memory tranches = new address[](3);
        tranches[0] = address(seniorTranche);
        tranches[1] = address(mezzTranche);
        tranches[2] = address(juniorTranche);

        vm.prank(trustee);
        vm.expectEmit(true, true, true, true);
        emit WaterfallInitialized(
            TEST_DEAL_ID,
            address(usdc),
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL
        );

        waterfall.initializeDealWaterfall(
            TEST_DEAL_ID,
            address(usdc),
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30, // 0.30% trustee fee
            20, // 0.20% servicer fee
            servicer
        );

        (
            bytes32 dealId,
            address paymentToken,
            ,
            WaterfallEngine.PrincipalPaydownStrategy strategy,
            ,
            uint256 totalOutstanding,
            bool isActive
        ) = waterfall.getDealWaterfallConfig(TEST_DEAL_ID);

        assertEq(dealId, TEST_DEAL_ID);
        assertEq(paymentToken, address(usdc));
        assertTrue(uint8(strategy) == uint8(WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL));
        assertEq(totalOutstanding, 100_000_000e18);
        assertTrue(isActive);
    }

    function test_initializeDealWaterfall_revert_notTrustee() public {
        address[] memory tranches = new address[](1);
        tranches[0] = address(seniorTranche);

        vm.prank(investor1);
        vm.expectRevert();
        waterfall.initializeDealWaterfall(
            TEST_DEAL_ID,
            address(usdc),
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30,
            20,
            servicer
        );
    }

    function test_initializeDealWaterfall_revert_alreadyInitialized() public {
        address[] memory tranches = new address[](1);
        tranches[0] = address(seniorTranche);

        vm.startPrank(trustee);
        waterfall.initializeDealWaterfall(
            TEST_DEAL_ID,
            address(usdc),
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30,
            20,
            servicer
        );

        vm.expectRevert();
        waterfall.initializeDealWaterfall(
            TEST_DEAL_ID,
            address(usdc),
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30,
            20,
            servicer
        );
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // WATERFALL DISTRIBUTION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_runWaterfall_interest_only() public {
        _initializeWaterfall();

        // Issue tokens to investors
        vm.startPrank(admin);
        seniorTranche.issue(investor1, 70_000_000e18);
        mezzTranche.issue(investor1, 20_000_000e18);
        juniorTranche.issue(investor1, 10_000_000e18);
        vm.stopPrank();

        // Mint USDC to trustee for distribution
        uint256 cashAmount = 1_000_000e6; // $1M in USDC
        usdc.mint(trustee, cashAmount);

        // Approve WaterfallEngine to spend USDC
        vm.prank(trustee);
        usdc.approve(address(waterfall), cashAmount);

        // Run waterfall
        vm.prank(trustee);
        waterfall.runWaterfall(TEST_DEAL_ID, 1, cashAmount);

        // Check that yield was distributed
        assertGt(seniorTranche.claimableYield(investor1), 0);
    }

    function test_runWaterfall_revert_notTrustee() public {
        _initializeWaterfall();

        vm.prank(investor1);
        vm.expectRevert();
        waterfall.runWaterfall(TEST_DEAL_ID, 1, 1_000_000e6);
    }

    function test_runWaterfall_revert_invalidPeriod() public {
        _initializeWaterfall();

        uint256 cashAmount = 1_000_000e6;
        usdc.mint(trustee, cashAmount);
        vm.startPrank(trustee);
        usdc.approve(address(waterfall), cashAmount);

        // Try to run period 0 (should fail)
        vm.expectRevert();
        waterfall.runWaterfall(TEST_DEAL_ID, 0, cashAmount);
        
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getDealWaterfallConfig() public {
        _initializeWaterfall();

        (
            bytes32 dealId,
            address paymentToken,
            ,
            ,
            ,
            uint256 totalOutstanding,
            bool isActive
        ) = waterfall.getDealWaterfallConfig(TEST_DEAL_ID);

        assertEq(dealId, TEST_DEAL_ID);
        assertEq(paymentToken, address(usdc));
        assertTrue(isActive);
        assertEq(totalOutstanding, 100_000_000e18);
    }

    function test_getTrancheAddresses() public {
        _initializeWaterfall();

        address[] memory trancheAddrs = waterfall.getTrancheAddresses(TEST_DEAL_ID);
        assertEq(trancheAddrs.length, 3);
        assertEq(trancheAddrs[0], address(seniorTranche));
        assertEq(trancheAddrs[1], address(mezzTranche));
        assertEq(trancheAddrs[2], address(juniorTranche));
    }

    function test_getAllDealIds() public {
        _initializeWaterfall();

        bytes32[] memory allDeals = waterfall.getAllDealIds();
        assertEq(allDeals.length, 1);
        assertEq(allDeals[0], TEST_DEAL_ID);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setRoleRegistry() public {
        RoleRegistry newRegistry = new RoleRegistry();
        
        vm.prank(admin);
        waterfall.setRoleRegistry(address(newRegistry));

        assertEq(address(waterfall.roleRegistry()), address(newRegistry));
    }

    function test_setServicerOracle() public {
        ServicerOracle newOracle = new ServicerOracle();
        
        vm.prank(admin);
        waterfall.setServicerOracle(address(newOracle));

        assertEq(address(waterfall.servicerOracle()), address(newOracle));
    }

    function test_pause_unpause() public {
        vm.startPrank(admin);
        waterfall.pause();
        assertTrue(waterfall.paused());

        waterfall.unpause();
        assertFalse(waterfall.paused());
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // HELPER FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    function _deployTranche(
        string memory trancheId,
        string memory symbol,
        uint256 faceValue,
        uint256 couponBps
    ) internal returns (RMBSTranche) {
        RMBSTranche.InitParams memory params = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: trancheId,
            name: string(abi.encodePacked("Test RMBS ", trancheId)),
            symbol: symbol,
            originalFaceValue: faceValue,
            couponRateBps: couponBps,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: admin,
            trustee: trustee
        });

        bytes memory initData = abi.encodeWithSelector(
            RMBSTranche.initialize.selector,
            params
        );

        ERC1967Proxy proxy = new ERC1967Proxy(address(trancheImpl), initData);
        return RMBSTranche(address(proxy));
    }

    function _initializeWaterfall() internal {
        address[] memory tranches = new address[](3);
        tranches[0] = address(seniorTranche);
        tranches[1] = address(mezzTranche);
        tranches[2] = address(juniorTranche);

        vm.prank(trustee);
        waterfall.initializeDealWaterfall(
            TEST_DEAL_ID,
            address(usdc),
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30, // 0.30% trustee fee
            20, // 0.20% servicer fee
            servicer
        );
    }
}

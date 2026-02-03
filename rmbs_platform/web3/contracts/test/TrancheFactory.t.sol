// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest, MockUSDC} from "./BaseTest.sol";
import {TrancheFactory} from "../src/tokens/TrancheFactory.sol";
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title TrancheFactoryTest
 * @notice Unit tests for TrancheFactory contract
 */
contract TrancheFactoryTest is BaseTest {
    TrancheFactory public factory;
    TrancheFactory public factoryImpl;
    RMBSTranche public trancheImpl;
    TransferValidator public validator;
    TransferValidator public validatorImpl;
    MockUSDC public usdc;

    bytes32 constant TEST_DEAL_ID = keccak256("DEAL_2024_TEST");
    string constant TEST_DEAL_NAME = "Test RMBS Deal 2024-1";

    event DealRegistered(
        bytes32 indexed dealId,
        string name,
        address indexed arranger,
        uint256 closingDate,
        uint256 maturityDate
    );

    event TrancheDeployed(
        bytes32 indexed dealId,
        string trancheId,
        address indexed trancheAddress,
        address indexed deployer,
        uint256 originalFaceValue
    );

    function setUp() public override {
        super.setUp();

        // Deploy Mock USDC
        usdc = new MockUSDC();

        // Deploy RMBSTranche implementation
        trancheImpl = new RMBSTranche();

        // Deploy TransferValidator
        validatorImpl = new TransferValidator();
        bytes memory validatorInitData = abi.encodeWithSelector(
            TransferValidator.initialize.selector,
            admin,
            complianceOfficer
        );
        address validatorProxy = address(new ERC1967Proxy(address(validatorImpl), validatorInitData));
        validator = TransferValidator(validatorProxy);

        // Deploy TrancheFactory
        factoryImpl = new TrancheFactory();
        bytes memory factoryInitData = abi.encodeWithSelector(
            TrancheFactory.initialize.selector,
            admin,
            address(trancheImpl),
            address(validator)
        );
        address factoryProxy = address(new ERC1967Proxy(address(factoryImpl), factoryInitData));
        factory = TrancheFactory(factoryProxy);

        // Grant roles
        vm.startPrank(admin);
        factory.grantRole(factory.DEPLOYER_ROLE(), arranger);
        validator.grantRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertEq(factory.trancheImplementation(), address(trancheImpl));
        assertTrue(factory.hasRole(factory.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(factory.hasRole(factory.DEPLOYER_ROLE(), arranger));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL REGISTRATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_registerDeal_success() public {
        vm.prank(arranger);
        vm.expectEmit(true, true, true, true);
        emit DealRegistered(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            arranger,
            block.timestamp,
            block.timestamp + 365 days * 5
        );
        
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        TrancheFactory.DealInfo memory dealInfo = factory.getDealInfo(TEST_DEAL_ID);

        assertEq(dealInfo.dealId, TEST_DEAL_ID);
        assertEq(dealInfo.name, TEST_DEAL_NAME);
        assertEq(dealInfo.arranger, arranger);
        assertTrue(dealInfo.isActive);
        assertEq(dealInfo.maturityDate, block.timestamp + 365 days * 5);
    }

    function test_registerDeal_revert_notDeployer() public {
        vm.prank(investor1);
        vm.expectRevert();
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );
    }

    function test_registerDeal_revert_duplicateDealId() public {
        vm.startPrank(arranger);
        
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        vm.expectRevert();
        factory.registerDeal(
            TEST_DEAL_ID,
            "Another Deal",
            block.timestamp,
            block.timestamp + 365 days * 5
        );
        
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TRANCHE DEPLOYMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_deployTranche_success() public {
        // Register deal first
        vm.prank(arranger);
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        // Prepare tranche params
        RMBSTranche.InitParams memory params = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: "CLASS_A",
            name: "Test RMBS Class A",
            symbol: "TRMBS-A",
            originalFaceValue: 100_000_000e18,
            couponRateBps: 500,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        vm.prank(arranger);
        vm.expectEmit(true, true, true, true);
        emit TrancheDeployed(
            TEST_DEAL_ID,
            "CLASS_A",
            address(0), // Will be determined at deployment
            arranger,
            100_000_000e18
        );

        address trancheAddr = factory.deployTranche(params);

        assertTrue(trancheAddr != address(0));
        assertTrue(factory.isDeployedTranche(trancheAddr));
        
        RMBSTranche tranche = RMBSTranche(trancheAddr);
        assertEq(tranche.name(), "Test RMBS Class A");
        assertEq(tranche.symbol(), "TRMBS-A");
        assertEq(tranche.originalFaceValue(), 100_000_000e18);
    }

    function test_deployTranche_revert_dealNotFound() public {
        RMBSTranche.InitParams memory params = RMBSTranche.InitParams({
            dealId: keccak256("NONEXISTENT_DEAL"),
            trancheId: "CLASS_A",
            name: "Test RMBS Class A",
            symbol: "TRMBS-A",
            originalFaceValue: 100_000_000e18,
            couponRateBps: 500,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        vm.prank(arranger);
        vm.expectRevert();
        factory.deployTranche(params);
    }

    function test_deployTranche_revert_notDeployer() public {
        vm.prank(arranger);
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        RMBSTranche.InitParams memory params = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: "CLASS_A",
            name: "Test RMBS Class A",
            symbol: "TRMBS-A",
            originalFaceValue: 100_000_000e18,
            couponRateBps: 500,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        vm.prank(investor1);
        vm.expectRevert();
        factory.deployTranche(params);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BATCH DEPLOYMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_deployTranches_success() public {
        // Register deal
        vm.prank(arranger);
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        // Create array of tranche params
        RMBSTranche.InitParams[] memory paramsArray = new RMBSTranche.InitParams[](3);
        
        paramsArray[0] = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: "CLASS_A",
            name: "Test RMBS Class A",
            symbol: "TRMBS-A",
            originalFaceValue: 70_000_000e18,
            couponRateBps: 400,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        paramsArray[1] = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: "CLASS_M",
            name: "Test RMBS Class M",
            symbol: "TRMBS-M",
            originalFaceValue: 20_000_000e18,
            couponRateBps: 600,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        paramsArray[2] = RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: "CLASS_B",
            name: "Test RMBS Class B",
            symbol: "TRMBS-B",
            originalFaceValue: 10_000_000e18,
            couponRateBps: 900,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        vm.prank(arranger);
        address[] memory tranches = factory.deployTranches(paramsArray);

        assertEq(tranches.length, 3);
        for (uint256 i = 0; i < tranches.length; i++) {
            assertTrue(tranches[i] != address(0));
            assertTrue(factory.isDeployedTranche(tranches[i]));
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getAllDeals() public {
        vm.startPrank(arranger);
        factory.registerDeal(TEST_DEAL_ID, TEST_DEAL_NAME, block.timestamp, block.timestamp + 365 days * 5);
        factory.registerDeal(keccak256("DEAL2"), "Deal 2", block.timestamp, block.timestamp + 365 days * 5);
        vm.stopPrank();

        bytes32[] memory allDeals = factory.getAllDeals();
        assertEq(allDeals.length, 2);
    }

    function test_getTranchesByDeal() public {
        // Register deal
        vm.prank(arranger);
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        // Deploy 2 tranches
        vm.startPrank(arranger);
        
        RMBSTranche.InitParams memory params1 = _createTestParams("CLASS_A", "TRMBS-A", 70_000_000e18);
        RMBSTranche.InitParams memory params2 = _createTestParams("CLASS_B", "TRMBS-B", 30_000_000e18);
        
        factory.deployTranche(params1);
        factory.deployTranche(params2);
        
        vm.stopPrank();

        address[] memory tranches = factory.getTranchesForDeal(TEST_DEAL_ID);
        assertEq(tranches.length, 2);
    }

    function test_updateDealStatus() public {
        vm.prank(arranger);
        factory.registerDeal(
            TEST_DEAL_ID,
            TEST_DEAL_NAME,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        vm.prank(arranger);
        factory.updateDealStatus(TEST_DEAL_ID, false);

        TrancheFactory.DealInfo memory dealInfo = factory.getDealInfo(TEST_DEAL_ID);
        assertFalse(dealInfo.isActive);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setTrancheImplementation() public {
        RMBSTranche newImpl = new RMBSTranche();

        vm.prank(admin);
        factory.setTrancheImplementation(address(newImpl));

        assertEq(factory.trancheImplementation(), address(newImpl));
    }

    function test_setTrancheImplementation_revert_notAdmin() public {
        RMBSTranche newImpl = new RMBSTranche();

        vm.prank(investor1);
        vm.expectRevert();
        factory.setTrancheImplementation(address(newImpl));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // HELPER FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    function _createTestParams(
        string memory trancheId,
        string memory symbol,
        uint256 faceValue
    ) internal view returns (RMBSTranche.InitParams memory) {
        return RMBSTranche.InitParams({
            dealId: TEST_DEAL_ID,
            trancheId: trancheId,
            name: string(abi.encodePacked("Test RMBS ", trancheId)),
            symbol: symbol,
            originalFaceValue: faceValue,
            couponRateBps: 500,
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 3,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });
    }
}

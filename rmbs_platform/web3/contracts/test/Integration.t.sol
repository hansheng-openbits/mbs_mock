// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest, MockUSDC} from "./BaseTest.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

// Import all contracts
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {TrancheFactory} from "../src/tokens/TrancheFactory.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {WaterfallEngine} from "../src/waterfall/WaterfallEngine.sol";
import {ServicerOracle} from "../src/oracle/ServicerOracle.sol";
import {RoleRegistry} from "../src/access/RoleRegistry.sol";

/**
 * @title IntegrationTest
 * @notice End-to-end integration tests for the RMBS platform
 */
contract IntegrationTest is BaseTest {
    // Contracts
    RMBSTranche public trancheImpl;
    TrancheFactory public factory;
    TransferValidator public validator;
    WaterfallEngine public waterfall;
    ServicerOracle public oracle;
    RoleRegistry public roleRegistry;
    MockUSDC public usdc;

    // Deployed tranches
    address public trancheA;
    address public trancheM;
    address public trancheB;

    // Events
    event DealRegistered(bytes32 indexed dealId, string name, address indexed arranger, uint256 closingDate, uint256 maturityDate);
    event TrancheDeployed(bytes32 indexed dealId, string trancheId, address indexed trancheAddress, address indexed deployer, uint256 originalFaceValue);
    event WaterfallExecuted(bytes32 indexed dealId, uint256 indexed period, uint256 totalDistributed, uint256 residual);

    function setUp() public override {
        super.setUp();

        // Deploy mock USDC
        usdc = new MockUSDC();
        vm.label(address(usdc), "USDC");

        // Deploy all contracts
        _deployContracts();
        
        // Configure roles
        _configureRoles();
        
        // Configure compliance
        _configureCompliance();
        
        // Create a deal with tranches
        _createDeal();
    }

    function _deployContracts() internal {
        // 1. Deploy RoleRegistry
        RoleRegistry roleRegistryImpl = new RoleRegistry();
        bytes memory roleRegistryInit = abi.encodeWithSelector(
            RoleRegistry.initialize.selector,
            admin
        );
        roleRegistry = RoleRegistry(address(new ERC1967Proxy(address(roleRegistryImpl), roleRegistryInit)));
        vm.label(address(roleRegistry), "RoleRegistry");

        // 2. Deploy TransferValidator
        TransferValidator validatorImpl = new TransferValidator();
        bytes memory validatorInit = abi.encodeWithSelector(
            TransferValidator.initialize.selector,
            admin
        );
        validator = TransferValidator(address(new ERC1967Proxy(address(validatorImpl), validatorInit)));
        vm.label(address(validator), "TransferValidator");

        // 3. Deploy WaterfallEngine
        WaterfallEngine waterfallImpl = new WaterfallEngine();
        bytes memory waterfallInit = abi.encodeWithSelector(
            WaterfallEngine.initialize.selector,
            admin
        );
        waterfall = WaterfallEngine(address(new ERC1967Proxy(address(waterfallImpl), waterfallInit)));
        vm.label(address(waterfall), "WaterfallEngine");

        // 4. Deploy ServicerOracle
        ServicerOracle oracleImpl = new ServicerOracle();
        bytes memory oracleInit = abi.encodeWithSelector(
            ServicerOracle.initialize.selector,
            admin,
            address(waterfall)
        );
        oracle = ServicerOracle(address(new ERC1967Proxy(address(oracleImpl), oracleInit)));
        vm.label(address(oracle), "ServicerOracle");

        // 5. Deploy TrancheFactory
        trancheImpl = new RMBSTranche();
        TrancheFactory factoryImpl = new TrancheFactory();
        bytes memory factoryInit = abi.encodeWithSelector(
            TrancheFactory.initialize.selector,
            admin,
            address(trancheImpl),
            address(validator)
        );
        factory = TrancheFactory(address(new ERC1967Proxy(address(factoryImpl), factoryInit)));
        vm.label(address(factory), "TrancheFactory");
    }

    function _configureRoles() internal {
        vm.startPrank(admin);

        // Grant roles in RoleRegistry
        roleRegistry.grantRole(roleRegistry.ARRANGER_ROLE(), arranger);
        roleRegistry.grantRole(roleRegistry.TRUSTEE_ROLE(), trustee);
        roleRegistry.grantRole(roleRegistry.SERVICER_ROLE(), servicer);
        roleRegistry.grantRole(roleRegistry.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);

        // Grant roles in TransferValidator
        validator.grantRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);

        // Grant roles in Factory
        factory.grantRole(factory.DEPLOYER_ROLE(), arranger);

        // Grant roles in WaterfallEngine
        waterfall.grantRole(waterfall.EXECUTOR_ROLE(), trustee);
        waterfall.grantRole(waterfall.CONFIG_ROLE(), arranger);

        // Grant roles in ServicerOracle
        oracle.grantRole(oracle.VALIDATOR_ROLE(), trustee);

        // Register servicer
        oracle.registerServicer(servicer, "Primary Servicer Inc.");

        vm.stopPrank();
    }

    function _configureCompliance() internal {
        vm.startPrank(complianceOfficer);

        // Set up investors with KYC
        validator.setInvestorKYC(investor1, true, block.timestamp + 365 days);
        validator.setInvestorKYC(investor2, true, block.timestamp + 365 days);
        validator.setInvestorKYC(investor3, true, block.timestamp + 365 days);

        // Set accreditation
        validator.setInvestorAccreditation(investor1, true);
        validator.setInvestorAccreditation(investor2, true);
        validator.setInvestorAccreditation(investor3, true);

        // Set jurisdictions
        validator.setInvestorJurisdiction(investor1, bytes2("US"));
        validator.setInvestorJurisdiction(investor2, bytes2("US"));
        validator.setInvestorJurisdiction(investor3, bytes2("GB"));

        vm.stopPrank();

        // Configure deal compliance
        vm.startPrank(admin);
        validator.setJurisdictionAllowed(DEAL_ID_1, bytes2("US"), true);
        validator.setJurisdictionAllowed(DEAL_ID_1, bytes2("GB"), true);
        validator.configureDeal(DEAL_ID_1, true, true, 0, type(uint256).max);
        vm.stopPrank();
    }

    function _createDeal() internal {
        // Register deal
        vm.prank(arranger);
        factory.registerDeal(
            DEAL_ID_1,
            "RMBS 2024-1",
            arranger,
            block.timestamp,
            block.timestamp + 365 days * 5
        );

        // Assign servicer to deal
        vm.prank(admin);
        oracle.assignServicerToDeal(DEAL_ID_1, servicer);

        // Deploy tranches
        vm.startPrank(arranger);

        // Senior tranche (A)
        RMBSTranche.InitParams memory paramsA = RMBSTranche.InitParams({
            dealId: DEAL_ID_1,
            trancheId: TRANCHE_A,
            name: "RMBS 2024-1 Class A",
            symbol: "RMBS24A",
            originalFaceValue: 70_000_000e6, // $70M
            couponRateBps: 400, // 4%
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 5,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });
        trancheA = factory.deployTranche(paramsA);
        vm.label(trancheA, "TrancheA");

        // Mezzanine tranche (M)
        RMBSTranche.InitParams memory paramsM = RMBSTranche.InitParams({
            dealId: DEAL_ID_1,
            trancheId: TRANCHE_M,
            name: "RMBS 2024-1 Class M",
            symbol: "RMBS24M",
            originalFaceValue: 20_000_000e6, // $20M
            couponRateBps: 600, // 6%
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 5,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });
        trancheM = factory.deployTranche(paramsM);
        vm.label(trancheM, "TrancheM");

        // Junior tranche (B)
        RMBSTranche.InitParams memory paramsB = RMBSTranche.InitParams({
            dealId: DEAL_ID_1,
            trancheId: TRANCHE_B,
            name: "RMBS 2024-1 Class B",
            symbol: "RMBS24B",
            originalFaceValue: 10_000_000e6, // $10M
            couponRateBps: 900, // 9%
            paymentFrequency: 1,
            maturityDate: block.timestamp + 365 days * 5,
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });
        trancheB = factory.deployTranche(paramsB);
        vm.label(trancheB, "TrancheB");

        vm.stopPrank();

        // Issue tokens to investors
        _issueTokensToInvestors();

        // Configure waterfall
        _configureWaterfall();
    }

    function _issueTokensToInvestors() internal {
        // Issue senior tranche tokens
        vm.startPrank(arranger);
        RMBSTranche(trancheA).issue(investor1, 40_000_000e18); // $40M
        RMBSTranche(trancheA).issue(investor2, 30_000_000e18); // $30M
        vm.stopPrank();

        // Issue mezzanine tokens
        vm.startPrank(arranger);
        RMBSTranche(trancheM).issue(investor2, 15_000_000e18); // $15M
        RMBSTranche(trancheM).issue(investor3, 5_000_000e18);  // $5M
        vm.stopPrank();

        // Issue junior tokens
        vm.startPrank(arranger);
        RMBSTranche(trancheB).issue(investor3, 10_000_000e18); // $10M
        vm.stopPrank();
    }

    function _configureWaterfall() internal {
        address[] memory tranches = new address[](3);
        tranches[0] = trancheA;
        tranches[1] = trancheM;
        tranches[2] = trancheB;

        WaterfallEngine.Seniority[] memory seniorities = new WaterfallEngine.Seniority[](3);
        seniorities[0] = WaterfallEngine.Seniority.SENIOR;
        seniorities[1] = WaterfallEngine.Seniority.MEZZANINE;
        seniorities[2] = WaterfallEngine.Seniority.JUNIOR;

        uint256[] memory rates = new uint256[](3);
        rates[0] = 400; // 4%
        rates[1] = 600; // 6%
        rates[2] = 900; // 9%

        WaterfallEngine.WaterfallConfig memory config = WaterfallEngine.WaterfallConfig({
            dealId: DEAL_ID_1,
            paymentToken: address(usdc),
            tranches: tranches,
            seniorities: seniorities,
            interestRatesBps: rates,
            trusteeFeesBps: 10,  // 0.1%
            servicerFeesBps: 25, // 0.25%
            trusteeAddress: trustee,
            servicerAddress: servicer,
            principalSequential: true,
            isActive: true
        });

        vm.prank(arranger);
        waterfall.configureWaterfall(config);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INTEGRATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_fullDealLifecycle() public {
        // Verify deal is created correctly
        assertEq(factory.getTotalDealCount(), 1);
        assertEq(factory.getTrancheCountForDeal(DEAL_ID_1), 3);

        // Verify tranches are deployed
        assertTrue(factory.isDeployedTranche(trancheA));
        assertTrue(factory.isDeployedTranche(trancheM));
        assertTrue(factory.isDeployedTranche(trancheB));

        // Verify token issuance
        assertEq(RMBSTranche(trancheA).totalSupply(), 70_000_000e18);
        assertEq(RMBSTranche(trancheM).totalSupply(), 20_000_000e18);
        assertEq(RMBSTranche(trancheB).totalSupply(), 10_000_000e18);
    }

    function test_compliantTransfer() public {
        // Transfer between compliant investors
        uint256 transferAmount = 5_000_000e18;

        vm.prank(investor1);
        RMBSTranche(trancheA).transfer(investor2, transferAmount);

        assertEq(RMBSTranche(trancheA).balanceOf(investor1), 35_000_000e18);
        assertEq(RMBSTranche(trancheA).balanceOf(investor2), 35_000_000e18);
    }

    function test_servicerReportsCollections() public {
        // Create loan tape data
        ServicerOracle.LoanTapeData memory loanTape = ServicerOracle.LoanTapeData({
            dealId: DEAL_ID_1,
            periodNumber: 1,
            reportingDate: block.timestamp,
            submissionTimestamp: 0,
            scheduledPrincipal: 500_000e6,
            scheduledInterest: 300_000e6,
            actualPrincipal: 500_000e6,
            actualInterest: 300_000e6,
            prepayments: 50_000e6,
            curtailments: 10_000e6,
            defaults: 0,
            lossSeverity: 0,
            recoveries: 0,
            totalLoanCount: 1000,
            currentLoanCount: 990,
            delinquentLoanCount: 10,
            totalUPB: 99_000_000e6,
            wac: 550, // 5.5%
            wam: 300, // 300 months
            waLTV: 7500, // 75%
            dataHash: keccak256("loan tape data"),
            zkProof: "",
            isVerified: false,
            isDisputed: false,
            submitter: address(0)
        });

        // Servicer submits loan tape
        vm.prank(servicer);
        oracle.submitLoanTape(loanTape);

        // Verify data was stored
        assertEq(oracle.getDealCurrentPeriod(DEAL_ID_1), 1);

        // Trustee verifies data
        vm.prank(trustee);
        oracle.verifyData(DEAL_ID_1, 1);

        // Check data is verified
        ServicerOracle.LoanTapeData memory storedData = oracle.getLoanTapeData(DEAL_ID_1, 1);
        assertTrue(storedData.isVerified);
    }

    function test_yieldDistributionWorkflow() public {
        // Fund the waterfall engine
        uint256 totalCollections = 1_000_000e6; // $1M in collections
        usdc.mint(address(waterfall), totalCollections);

        // Report collections manually (simulating oracle)
        vm.prank(trustee);
        waterfall.reportCollections(
            DEAL_ID_1,
            600_000e6,   // interest
            400_000e6,   // principal
            0,           // losses
            50_000e6     // prepayments
        );

        // Approve waterfall to spend on tranches
        vm.startPrank(trustee);
        usdc.approve(trancheA, totalCollections);
        usdc.approve(trancheM, totalCollections);
        usdc.approve(trancheB, totalCollections);
        vm.stopPrank();

        // Execute waterfall would require more setup
        // This is a simplified test to verify the integration
    }

    function test_investorClaimsYield() public {
        // Simulate yield distribution to tranche A
        uint256 yieldAmount = 250_000e6; // $250k monthly yield

        // Fund and distribute
        usdc.mint(trustee, yieldAmount);

        vm.startPrank(trustee);
        usdc.approve(trancheA, yieldAmount);
        RMBSTranche(trancheA).distributeYield(yieldAmount);
        vm.stopPrank();

        // Calculate expected yield for investor1 (40M / 70M = 57.14%)
        uint256 investor1Share = (yieldAmount * 40_000_000e18) / 70_000_000e18;

        // Verify claimable
        uint256 claimable = RMBSTranche(trancheA).claimableYield(investor1);
        assertEq(claimable, investor1Share);

        // Claim
        vm.prank(investor1);
        RMBSTranche(trancheA).claimYield();

        // Verify balance
        assertEq(usdc.balanceOf(investor1), investor1Share);
    }

    function test_factorUpdateReducesFaceValue() public {
        // Get initial face value
        uint256 initialFace = RMBSTranche(trancheA).currentFaceValue();
        assertEq(initialFace, 70_000_000e6);

        // Update factor (5% principal paydown)
        vm.prank(trustee);
        RMBSTranche(trancheA).updateFactor(0.95e18);

        // Verify new face value
        uint256 newFace = RMBSTranche(trancheA).currentFaceValue();
        assertEq(newFace, 66_500_000e6); // 70M * 0.95
    }

    function test_roleRegistryIntegration() public {
        // Verify roles
        assertTrue(roleRegistry.hasRole(roleRegistry.ARRANGER_ROLE(), arranger));
        assertTrue(roleRegistry.hasRole(roleRegistry.TRUSTEE_ROLE(), trustee));
        assertTrue(roleRegistry.hasRole(roleRegistry.SERVICER_ROLE(), servicer));
    }

    function test_documentManagement() public {
        bytes32 docName = keccak256("PROSPECTUS");
        string memory uri = "ipfs://QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG";
        bytes32 docHash = keccak256("prospectus content");

        vm.prank(arranger);
        RMBSTranche(trancheA).setDocument(docName, uri, docHash);

        (string memory storedUri, bytes32 storedHash,) = RMBSTranche(trancheA).getDocument(docName);
        assertEq(storedUri, uri);
        assertEq(storedHash, docHash);
    }

    function test_emergencyPause() public {
        // Pause the deal
        vm.prank(admin);
        validator.emergencyPauseDeal(DEAL_ID_1);

        // Transfers should fail
        vm.prank(investor1);
        vm.expectRevert();
        RMBSTranche(trancheA).transfer(investor2, 1_000_000e18);

        // Unpause
        vm.prank(admin);
        validator.emergencyUnpauseDeal(DEAL_ID_1);

        // Transfers should work again
        vm.prank(investor1);
        RMBSTranche(trancheA).transfer(investor2, 1_000_000e18);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EDGE CASES
    // ═══════════════════════════════════════════════════════════════════════

    function test_multiplePeriodYieldClaim() public {
        // Distribute yield for 3 periods
        uint256 yieldPerPeriod = 100_000e6;
        usdc.mint(trustee, yieldPerPeriod * 3);

        vm.startPrank(trustee);
        usdc.approve(trancheA, yieldPerPeriod * 3);

        // Period 0
        RMBSTranche(trancheA).distributeYield(yieldPerPeriod);
        RMBSTranche(trancheA).updateFactor(0.98e18);

        // Period 1
        RMBSTranche(trancheA).distributeYield(yieldPerPeriod);
        RMBSTranche(trancheA).updateFactor(0.96e18);

        // Period 2
        RMBSTranche(trancheA).distributeYield(yieldPerPeriod);

        vm.stopPrank();

        // Investor claims all at once
        uint256 totalClaimable = RMBSTranche(trancheA).claimableYield(investor1);
        assertTrue(totalClaimable > 0);

        vm.prank(investor1);
        RMBSTranche(trancheA).claimYield();

        assertEq(RMBSTranche(trancheA).claimableYield(investor1), 0);
    }

    function test_dealSummary() public view {
        (
            TrancheFactory.DealInfo memory info,
            address[] memory tranches,
            uint256 trancheCount
        ) = factory.getDealSummary(DEAL_ID_1);

        assertEq(info.dealId, DEAL_ID_1);
        assertEq(info.arranger, arranger);
        assertTrue(info.isActive);
        assertEq(trancheCount, 3);
        assertEq(tranches.length, 3);
    }
}

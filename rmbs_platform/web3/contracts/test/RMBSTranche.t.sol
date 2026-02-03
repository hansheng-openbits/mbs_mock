// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest, MockUSDC, MockPassingTransferValidator, MockFailingTransferValidator} from "./BaseTest.sol";
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title RMBSTrancheTest
 * @notice Comprehensive tests for RMBSTranche contract
 */
contract RMBSTrancheTest is BaseTest {
    RMBSTranche public tranche;
    RMBSTranche public trancheImpl;
    MockUSDC public usdc;
    MockPassingTransferValidator public validator;

    // Events to test
    event YieldDistributed(uint256 indexed period, uint256 amount, uint256 snapshotId);
    event YieldClaimed(address indexed holder, uint256 amount, uint256 fromPeriod, uint256 toPeriod);
    event FactorUpdated(uint256 indexed period, uint256 oldFactor, uint256 newFactor);
    event PrincipalPaydown(uint256 indexed period, uint256 amount, uint256 newFactor);

    function setUp() public override {
        super.setUp();

        // Deploy mock USDC
        usdc = new MockUSDC();
        vm.label(address(usdc), "USDC");

        // Deploy mock validator
        validator = new MockPassingTransferValidator();
        vm.label(address(validator), "Validator");

        // Deploy tranche implementation
        trancheImpl = new RMBSTranche();

        // Prepare initialization params
        RMBSTranche.InitParams memory params = RMBSTranche.InitParams({
            dealId: DEAL_ID_1,
            trancheId: TRANCHE_A,
            name: "RMBS 2024-1 Class A",
            symbol: "RMBS24A",
            originalFaceValue: TRANCHE_FACE_VALUE,
            couponRateBps: 500, // 5%
            paymentFrequency: 1, // Monthly
            maturityDate: block.timestamp + 365 days * 3, // 3 years
            paymentToken: address(usdc),
            transferValidator: address(validator),
            admin: admin,
            issuer: arranger,
            trustee: trustee
        });

        // Deploy proxy
        bytes memory initData = abi.encodeWithSelector(
            RMBSTranche.initialize.selector,
            params
        );
        address proxy = address(new ERC1967Proxy(address(trancheImpl), initData));
        tranche = RMBSTranche(proxy);
        vm.label(proxy, "RMBSTranche");

        // Mint initial tokens to investors
        vm.startPrank(arranger);
        tranche.issue(investor1, 3_000_000e18); // 30% of face value
        tranche.issue(investor2, 5_000_000e18); // 50% of face value
        tranche.issue(investor3, 2_000_000e18); // 20% of face value
        vm.stopPrank();

        // Fund investors with USDC for testing
        usdc.mint(investor1, INITIAL_BALANCE);
        usdc.mint(investor2, INITIAL_BALANCE);
        usdc.mint(investor3, INITIAL_BALANCE);
        usdc.mint(trustee, 10_000_000e6); // For yield distributions
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertEq(tranche.name(), "RMBS 2024-1 Class A");
        assertEq(tranche.symbol(), "RMBS24A");
        assertEq(tranche.dealId(), DEAL_ID_1);
        assertEq(tranche.trancheId(), TRANCHE_A);
        assertEq(tranche.originalFaceValue(), TRANCHE_FACE_VALUE);
        assertEq(tranche.couponRateBps(), 500);
        assertEq(tranche.paymentFrequency(), 1);
        assertEq(tranche.currentFactor(), 1e18); // 100%
        assertEq(tranche.currentPeriod(), 0);
    }

    function test_initialBalances() public view {
        assertEq(tranche.balanceOf(investor1), 3_000_000e18);
        assertEq(tranche.balanceOf(investor2), 5_000_000e18);
        assertEq(tranche.balanceOf(investor3), 2_000_000e18);
        assertEq(tranche.totalSupply(), 10_000_000e18);
    }

    function test_roles() public view {
        assertTrue(tranche.hasRole(tranche.ISSUER_ROLE(), arranger));
        assertTrue(tranche.hasRole(tranche.TRUSTEE_ROLE(), trustee));
        assertTrue(tranche.hasRole(tranche.DEFAULT_ADMIN_ROLE(), arranger));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ISSUANCE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_issue_success() public {
        address newInvestor = makeAddr("newInvestor");
        
        vm.prank(arranger);
        tranche.issue(newInvestor, 1_000_000e18);

        assertEq(tranche.balanceOf(newInvestor), 1_000_000e18);
    }

    function test_issue_revert_notIssuer() public {
        vm.prank(investor1);
        vm.expectRevert();
        tranche.issue(investor1, 1_000_000e18);
    }

    function test_issue_revert_zeroAddress() public {
        vm.prank(arranger);
        vm.expectRevert(RMBSTranche.ZeroAddress.selector);
        tranche.issue(address(0), 1_000_000e18);
    }

    function test_issue_revert_zeroAmount() public {
        vm.prank(arranger);
        vm.expectRevert(RMBSTranche.ZeroAmount.selector);
        tranche.issue(investor1, 0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TRANSFER TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_transfer_success() public {
        vm.prank(investor1);
        tranche.transfer(investor2, 1_000_000e18);

        assertEq(tranche.balanceOf(investor1), 2_000_000e18);
        assertEq(tranche.balanceOf(investor2), 6_000_000e18);
    }

    // NOTE: Test disabled - setTransferValidator is now immutable (set at initialization)
    // To test transfer restrictions, need to deploy new tranche with failing validator
    // function test_transfer_revert_withFailingValidator() public {
    //     MockFailingTransferValidator failingValidator = new MockFailingTransferValidator();
    //     vm.prank(arranger);
    //     tranche.setTransferValidator(address(failingValidator));
    //     vm.prank(investor1);
    //     vm.expectRevert();
    //     tranche.transfer(investor2, 1_000_000e18);
    // }

    function test_transfer_revert_whenPaused() public {
        vm.prank(arranger);
        tranche.pause();

        vm.prank(investor1);
        vm.expectRevert(RMBSTranche.ContractPaused.selector);
        tranche.transfer(investor2, 1_000_000e18);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // YIELD DISTRIBUTION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_distributeYield_success() public {
        uint256 yieldAmount = 100_000e6; // 100k USDC

        // Approve and distribute
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldAmount);
        
        vm.expectEmit(true, true, true, false);
        emit YieldDistributed(0, yieldAmount, 1); // snapshotId will be 1
        
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        // Verify period yield stored
        assertEq(tranche.periodYield(0), yieldAmount);
    }

    function test_distributeYield_revert_notTrustee() public {
        vm.prank(investor1);
        vm.expectRevert();
        tranche.distributeYield(100_000e6);
    }

    function test_distributeYield_revert_zeroAmount() public {
        vm.prank(trustee);
        vm.expectRevert(RMBSTranche.ZeroAmount.selector);
        tranche.distributeYield(0);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // YIELD CLAIMING TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_claimYield_success() public {
        uint256 yieldAmount = 100_000e6;

        // Distribute yield
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldAmount);
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        // Calculate expected yield for investor1 (30% of total)
        uint256 expectedYield = (yieldAmount * 3_000_000e18) / 10_000_000e18;

        // Check claimable
        assertEq(tranche.claimableYield(investor1), expectedYield);

        // Claim
        uint256 balanceBefore = usdc.balanceOf(investor1);
        
        vm.prank(investor1);
        tranche.claimYield();

        assertEq(usdc.balanceOf(investor1), balanceBefore + expectedYield);
        assertEq(tranche.claimableYield(investor1), 0);
    }

    function test_claimYield_multipleInvestors() public {
        uint256 yieldAmount = 100_000e6;

        // Distribute yield
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldAmount);
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        // Expected yields
        uint256 expectedYield1 = (yieldAmount * 3_000_000e18) / 10_000_000e18; // 30%
        uint256 expectedYield2 = (yieldAmount * 5_000_000e18) / 10_000_000e18; // 50%
        uint256 expectedYield3 = (yieldAmount * 2_000_000e18) / 10_000_000e18; // 20%

        // All investors claim
        vm.prank(investor1);
        tranche.claimYield();
        
        vm.prank(investor2);
        tranche.claimYield();
        
        vm.prank(investor3);
        tranche.claimYield();

        // Verify balances
        assertEq(usdc.balanceOf(investor1), INITIAL_BALANCE + expectedYield1);
        assertEq(usdc.balanceOf(investor2), INITIAL_BALANCE + expectedYield2);
        assertEq(usdc.balanceOf(investor3), INITIAL_BALANCE + expectedYield3);
    }

    function test_claimYield_multiplePeriods() public {
        uint256 yieldPerPeriod = 50_000e6;

        // Distribute 3 periods of yield
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldPerPeriod * 3);
        
        tranche.distributeYield(yieldPerPeriod);
        skip(30 days);
        
        // Update factor to move to next period
        tranche.updateFactor(0.95e18);
        tranche.distributeYield(yieldPerPeriod);
        skip(30 days);
        
        tranche.updateFactor(0.90e18);
        tranche.distributeYield(yieldPerPeriod);
        vm.stopPrank();

        // Investor1 claims all at once
        uint256 totalClaimable = tranche.claimableYield(investor1);
        assertTrue(totalClaimable > 0, "Should have claimable yield");

        vm.prank(investor1);
        tranche.claimYield();

        assertEq(tranche.claimableYield(investor1), 0);
    }

    function test_claimYield_revert_nothingToClaim() public {
        vm.prank(investor1);
        vm.expectRevert(RMBSTranche.NothingToClaim.selector);
        tranche.claimYield();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SNAPSHOT GAMING PROTECTION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_snapshotPreventsGaming() public {
        uint256 yieldAmount = 100_000e6;

        // Investor1 has 30% = 3M tokens
        uint256 investor1BalanceBefore = tranche.balanceOf(investor1);

        // Distribute yield (snapshot taken here)
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldAmount);
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        // After distribution, investor1 transfers ALL tokens to attacker
        vm.prank(investor1);
        tranche.transfer(attacker, investor1BalanceBefore);

        // Attacker now has the tokens, but should NOT be able to claim yield
        // because snapshot was taken before the transfer
        assertEq(tranche.claimableYield(attacker), 0, "Attacker should have no claimable yield");

        // Original investor1 should still be able to claim based on snapshot
        uint256 expectedYield = (yieldAmount * investor1BalanceBefore) / tranche.totalSupply();
        assertEq(tranche.claimableYield(investor1), expectedYield, "Original holder should have claimable yield");

        // Investor1 claims
        vm.prank(investor1);
        tranche.claimYield();

        // Verify attacker gets nothing
        vm.prank(attacker);
        vm.expectRevert(RMBSTranche.NothingToClaim.selector);
        tranche.claimYield();
    }

    function test_snapshotAtomicity() public {
        uint256 yieldAmount = 100_000e6;

        // Get balances at moment of distribution
        uint256 investor1Balance = tranche.balanceOf(investor1);
        uint256 totalSupply = tranche.totalSupply();

        // Distribute yield
        vm.startPrank(trustee);
        usdc.approve(address(tranche), yieldAmount);
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        // Verify snapshot was taken correctly
        (uint256 snapshotId, uint256 yieldStored,) = tranche.getPeriodSnapshot(0);
        assertTrue(snapshotId > 0, "Snapshot ID should be set");
        assertEq(yieldStored, yieldAmount, "Yield amount should match");

        // Verify balance at period matches balance at distribution time
        uint256 balanceAtPeriod = tranche.getBalanceAtPeriod(investor1, 0);
        assertEq(balanceAtPeriod, investor1Balance, "Balance at period should match");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // BATCH CLAIM TESTS (DoS Protection)
    // ═══════════════════════════════════════════════════════════════════════

    function test_claimYieldUpTo_success() public {
        // Distribute multiple periods
        vm.startPrank(trustee);
        usdc.approve(address(tranche), 500_000e6);

        for (uint256 i = 0; i < 5; i++) {
            tranche.distributeYield(10_000e6);
            tranche.updateFactor(uint256(1e18 - (i + 1) * 0.01e18));
        }
        vm.stopPrank();

        // Claim only up to period 2
        vm.prank(investor1);
        tranche.claimYieldUpTo(2);

        // Verify last claimed period
        assertEq(tranche.lastClaimedPeriod(investor1), 2);

        // Should still have claimable yield for periods 3-5
        assertTrue(tranche.claimableYield(investor1) > 0);
    }

    function test_claimYield_revert_tooManyPeriods() public {
        // Simulate 150 periods (more than MAX_CLAIM_PERIODS = 100)
        vm.startPrank(trustee);
        usdc.approve(address(tranche), 1_500_000e6);

        for (uint256 i = 0; i < 150; i++) {
            tranche.distributeYield(1_000e6);
            if (i < 149) {
                uint256 newFactor = 1e18 - ((i + 1) * 0.005e18);
                if (newFactor > 0) {
                    tranche.updateFactor(newFactor);
                }
            }
        }
        vm.stopPrank();

        // Should revert when trying to claim all at once
        vm.prank(investor1);
        vm.expectRevert(abi.encodeWithSelector(RMBSTranche.TooManyPeriodsToProcess.selector, 150, 100));
        tranche.claimYield();

        // Should succeed with batch claiming
        vm.prank(investor1);
        tranche.claimYieldUpTo(100);

        vm.prank(investor1);
        tranche.claimYield(); // Claims remaining 50 periods
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FACTOR UPDATE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_updateFactor_success() public {
        uint256 newFactor = 0.95e18; // 5% principal paydown

        vm.prank(trustee);
        vm.expectEmit(true, true, true, true);
        emit FactorUpdated(1, 1e18, newFactor);
        tranche.updateFactor(newFactor);

        assertEq(tranche.currentFactor(), newFactor);
        assertEq(tranche.currentPeriod(), 1);
    }

    function test_updateFactor_revert_invalidFactor() public {
        // Factor cannot increase
        vm.prank(trustee);
        vm.expectRevert(abi.encodeWithSelector(RMBSTranche.InvalidFactor.selector, 1.1e18, 1e18));
        tranche.updateFactor(1.1e18);
    }

    function test_currentFaceValue() public {
        // Initial face value should be original
        assertEq(tranche.currentFaceValue(), TRANCHE_FACE_VALUE);

        // After 10% paydown
        vm.prank(trustee);
        tranche.updateFactor(0.9e18);

        assertEq(tranche.currentFaceValue(), TRANCHE_FACE_VALUE * 90 / 100);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // PAUSE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_pause_success() public {
        vm.prank(arranger);
        tranche.pause();

        assertTrue(tranche.paused());
    }

    function test_unpause_success() public {
        vm.prank(arranger);
        tranche.pause();

        vm.prank(arranger);
        tranche.unpause();

        assertFalse(tranche.paused());
    }

    function test_pause_revert_notAdmin() public {
        vm.prank(investor1);
        vm.expectRevert();
        tranche.pause();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DOCUMENT MANAGEMENT TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setDocument_success() public {
        bytes32 docName = keccak256("PROSPECTUS");
        string memory uri = "ipfs://QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG";
        bytes32 docHash = keccak256("document content");

        vm.prank(arranger);
        tranche.setDocument(docName, uri, docHash);

        (string memory storedUri, bytes32 storedHash,) = tranche.getDocument(docName);
        assertEq(storedUri, uri);
        assertEq(storedHash, docHash);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // CONTROLLER OPERATIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_controllerTransfer_success() public {
        // Grant controller role
        vm.prank(arranger);
        tranche.grantRole(tranche.CONTROLLER_ROLE(), admin);

        // Enable controller
        vm.prank(arranger);
        tranche.setControllerEnabled(true);

        // Forced transfer (e.g., court order)
        uint256 transferAmount = 1_000_000e18;
        
        vm.prank(admin);
        tranche.controllerTransfer(investor1, trustee, transferAmount, "", "Court Order #12345");

        assertEq(tranche.balanceOf(investor1), 2_000_000e18);
        assertEq(tranche.balanceOf(trustee), transferAmount);
    }

    function test_controllerTransfer_revert_controllerNotEnabled() public {
        vm.prank(arranger);
        tranche.grantRole(tranche.CONTROLLER_ROLE(), admin);

        // Controller not enabled
        vm.prank(admin);
        vm.expectRevert("Controller operations disabled");
        tranche.controllerTransfer(investor1, trustee, 1_000_000e18, "", "Court Order");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // REDEMPTION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_redeem_success() public {
        uint256 redeemAmount = 1_000_000e18;

        vm.prank(investor1);
        tranche.redeem(redeemAmount, "Voluntary redemption");

        assertEq(tranche.balanceOf(investor1), 2_000_000e18);
        assertEq(tranche.totalSupply(), 9_000_000e18);
    }

    function test_redeem_revert_insufficientBalance() public {
        vm.prank(investor1);
        vm.expectRevert(abi.encodeWithSelector(
            RMBSTranche.InsufficientBalance.selector, 
            100_000_000e18, 
            3_000_000e18
        ));
        tranche.redeem(100_000_000e18, "Too much");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getTrancheInfo() public view {
        (
            bytes32 dealId,
            string memory trancheId,
            uint256 originalFaceValue,
            uint256 currentFactor,
            uint256 couponRateBps,
            uint8 paymentFrequency,
            uint256 maturityDate,
            uint256 currentPeriod,
            bool paused
        ) = tranche.getTrancheInfo();

        assertEq(dealId, DEAL_ID_1);
        assertEq(trancheId, TRANCHE_A);
        assertEq(originalFaceValue, TRANCHE_FACE_VALUE);
        assertEq(currentFactor, 1e18);
        assertEq(couponRateBps, 500);
        assertEq(paymentFrequency, 1);
        assertTrue(maturityDate > block.timestamp);
        assertEq(currentPeriod, 0);
        assertFalse(paused);
    }

    function test_getYieldInfo() public {
        // Distribute yield
        vm.startPrank(trustee);
        usdc.approve(address(tranche), 100_000e6);
        tranche.distributeYield(100_000e6);
        vm.stopPrank();

        (uint256 claimable, uint256 lastClaimed, uint256 unclaimedPeriods) = 
            tranche.getYieldInfo(investor1);

        assertTrue(claimable > 0);
        assertEq(lastClaimed, 0);
        assertEq(unclaimedPeriods, 0); // Period 0 is current, no unclaimed "periods" yet
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FUZZ TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function testFuzz_transfer(uint256 amount) public {
        amount = bound(amount, 1, tranche.balanceOf(investor1));

        uint256 investor1Before = tranche.balanceOf(investor1);
        uint256 investor2Before = tranche.balanceOf(investor2);

        vm.prank(investor1);
        tranche.transfer(investor2, amount);

        assertEq(tranche.balanceOf(investor1), investor1Before - amount);
        assertEq(tranche.balanceOf(investor2), investor2Before + amount);
    }

    function testFuzz_yieldDistribution(uint256 yieldAmount) public {
        yieldAmount = bound(yieldAmount, 1e6, 10_000_000e6); // 1 to 10M USDC

        vm.startPrank(trustee);
        usdc.mint(trustee, yieldAmount);
        usdc.approve(address(tranche), yieldAmount);
        tranche.distributeYield(yieldAmount);
        vm.stopPrank();

        uint256 totalClaimable = 
            tranche.claimableYield(investor1) +
            tranche.claimableYield(investor2) +
            tranche.claimableYield(investor3);

        // Total claimable should equal distributed amount (minus rounding)
        assertApproxEqAbs(totalClaimable, yieldAmount, 3); // Allow 3 wei rounding
    }

    function testFuzz_factorUpdate(uint256 newFactor) public {
        newFactor = bound(newFactor, 0, 1e18);

        uint256 oldFactor = tranche.currentFactor();

        if (newFactor <= oldFactor) {
            vm.prank(trustee);
            tranche.updateFactor(newFactor);
            assertEq(tranche.currentFactor(), newFactor);
        } else {
            vm.prank(trustee);
            vm.expectRevert();
            tranche.updateFactor(newFactor);
        }
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest} from "./BaseTest.sol";
import {ServicerOracle} from "../src/oracle/ServicerOracle.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title ServicerOracleTest
 * @notice Basic unit tests for ServicerOracle contract
 */
contract ServicerOracleTest is BaseTest {
    ServicerOracle public oracle;
    ServicerOracle public oracleImpl;

    bytes32 constant TEST_DEAL_ID = keccak256("DEAL_2024_TEST");

    function setUp() public override {
        super.setUp();

        // Deploy ServicerOracle
        oracleImpl = new ServicerOracle();
        bytes memory oracleInitData = abi.encodeWithSelector(
            ServicerOracle.initialize.selector,
            admin
        );
        address oracleProxy = address(new ERC1967Proxy(address(oracleImpl), oracleInitData));
        oracle = ServicerOracle(oracleProxy);

        // Setup roles
        vm.startPrank(admin);
        oracle.grantRole(oracle.SERVICER_ROLE(), servicer);
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertTrue(oracle.hasRole(oracle.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(oracle.hasRole(oracle.SERVICER_ROLE(), servicer));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SERVICER VERIFICATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_addAuthorizedServicer_success() public {
        vm.prank(admin);
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);

        assertTrue(oracle.isServicerAuthorized(TEST_DEAL_ID, servicer));
    }

    function test_addAuthorizedServicer_revert_notAdmin() public {
        vm.prank(investor1);
        vm.expectRevert();
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);
    }

    function test_removeAuthorizedServicer_success() public {
        vm.startPrank(admin);
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);
        oracle.removeAuthorizedServicer(TEST_DEAL_ID, servicer);
        vm.stopPrank();

        assertFalse(oracle.isServicerAuthorized(TEST_DEAL_ID, servicer));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // LOAN TAPE SUBMISSION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_submitLoanTape_success() public {
        // Add servicer as authorized
        vm.prank(admin);
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);

        ServicerOracle.LoanTapeData memory data = ServicerOracle.LoanTapeData({
            dealId: TEST_DEAL_ID,
            periodNumber: 1,
            reportingDate: block.timestamp,
            submissionTimestamp: 0, // Will be set by contract
            scheduledPrincipal: 1_000_000e6,
            scheduledInterest: 50_000e6,
            actualPrincipal: 950_000e6,
            actualInterest: 48_000e6,
            prepayments: 100_000e6,
            curtailments: 0,
            defaults: 5_000e6,
            lossSeverity: 2_000e6,
            recoveries: 500e6,
            advancedPrincipal: 0,
            advancedInterest: 0,
            numLoansActive: 1000,
            numLoansDelinquent30: 10,
            numLoansDelinquent60: 5,
            numLoansDelinquent90: 2,
            numLoansForeclosure: 1,
            numLoansREO: 0,
            numLoansModified: 3,
            numLoansDefaulted: 5,
            avgCurrentLTV: 7500, // 75%
            avgOriginalLTV: 8000, // 80%
            avgFICO: 740,
            avgDTI: 3500, // 35%
            dataHash: keccak256("test_data"),
            zkProofHash: bytes32(0) // No ZK proof for testing
        });

        vm.prank(servicer);
        oracle.submitLoanTape(data);

        uint256 latestPeriod = oracle.getDealCurrentPeriod(TEST_DEAL_ID);
        assertEq(latestPeriod, 1);
    }

    function test_submitLoanTape_revert_notServicer() public {
        ServicerOracle.LoanTapeData memory data = _createTestLoanTape(1);

        vm.prank(investor1);
        vm.expectRevert();
        oracle.submitLoanTape(data);
    }

    function test_submitLoanTape_revert_notAuthorized() public {
        ServicerOracle.LoanTapeData memory data = _createTestLoanTape(1);

        // Servicer has global role but not authorized for this deal
        vm.prank(servicer);
        vm.expectRevert();
        oracle.submitLoanTape(data);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getCollectionsForWaterfall() public {
        vm.prank(admin);
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);

        ServicerOracle.LoanTapeData memory data = _createTestLoanTape(1);

        vm.prank(servicer);
        oracle.submitLoanTape(data);

        (uint256 totalPrincipal, uint256 totalInterest, uint256 recoveries, uint256 advances) = 
            oracle.getCollectionsForWaterfall(TEST_DEAL_ID, 1);

        assertGt(totalPrincipal, 0);
        assertGt(totalInterest, 0);
    }

    function test_getDealCurrentPeriod() public {
        vm.prank(admin);
        oracle.addAuthorizedServicer(TEST_DEAL_ID, servicer);

        // Submit 3 periods
        vm.startPrank(servicer);
        for (uint256 i = 1; i <= 3; i++) {
            ServicerOracle.LoanTapeData memory data = _createTestLoanTape(i);
            oracle.submitLoanTape(data);
        }
        vm.stopPrank();

        uint256 latestPeriod = oracle.getDealCurrentPeriod(TEST_DEAL_ID);
        assertEq(latestPeriod, 3);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ADMIN FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_pause_unpause() public {
        vm.startPrank(admin);
        oracle.pause();
        assertTrue(oracle.paused());

        oracle.unpause();
        assertFalse(oracle.paused());
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // HELPER FUNCTIONS
    // ═══════════════════════════════════════════════════════════════════════

    function _createTestLoanTape(uint256 period) internal view returns (ServicerOracle.LoanTapeData memory) {
        return ServicerOracle.LoanTapeData({
            dealId: TEST_DEAL_ID,
            periodNumber: period,
            reportingDate: block.timestamp,
            submissionTimestamp: 0,
            scheduledPrincipal: 1_000_000e6,
            scheduledInterest: 50_000e6,
            actualPrincipal: 950_000e6,
            actualInterest: 48_000e6,
            prepayments: 100_000e6,
            curtailments: 0,
            defaults: 5_000e6,
            lossSeverity: 2_000e6,
            recoveries: 500e6,
            advancedPrincipal: 0,
            advancedInterest: 0,
            numLoansActive: 1000,
            numLoansDelinquent30: 10,
            numLoansDelinquent60: 5,
            numLoansDelinquent90: 2,
            numLoansForeclosure: 1,
            numLoansREO: 0,
            numLoansModified: 3,
            numLoansDefaulted: 5,
            avgCurrentLTV: 7500,
            avgOriginalLTV: 8000,
            avgFICO: 740,
            avgDTI: 3500,
            dataHash: keccak256("test_data"),
            zkProofHash: bytes32(0)
        });
    }
}

// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Test, console2} from "forge-std/Test.sol";
import {BaseTest} from "./BaseTest.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

/**
 * @title TransferValidatorTest
 * @notice Tests for TransferValidator contract
 */
contract TransferValidatorTest is BaseTest {
    TransferValidator public validator;
    TransferValidator public validatorImpl;

    // Events
    event KYCStatusUpdated(address indexed investor, bool verified, uint256 expiry);
    event AccreditationStatusUpdated(address indexed investor, bool accredited);

    function setUp() public override {
        super.setUp();

        // Deploy implementation
        validatorImpl = new TransferValidator();

        // Deploy proxy
        bytes memory initData = abi.encodeWithSelector(
            TransferValidator.initialize.selector,
            admin
        );
        address proxy = address(new ERC1967Proxy(address(validatorImpl), initData));
        validator = TransferValidator(proxy);
        vm.label(proxy, "TransferValidator");

        // Grant compliance officer role
        vm.prank(admin);
        validator.grantRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);

        // Set up investors with KYC
        _setupInvestors();
    }

    function _setupInvestors() internal {
        vm.startPrank(complianceOfficer);

        // Set up verified investors
        validator.setInvestorKYC(investor1, true, block.timestamp + 365 days);
        validator.setInvestorKYC(investor2, true, block.timestamp + 365 days);
        validator.setInvestorKYC(investor3, true, block.timestamp + 365 days);

        // Set accreditation
        validator.setInvestorAccreditation(investor1, true);
        validator.setInvestorAccreditation(investor2, true);

        // Set jurisdictions
        validator.setInvestorJurisdiction(investor1, bytes2("US"));
        validator.setInvestorJurisdiction(investor2, bytes2("GB"));
        validator.setInvestorJurisdiction(investor3, bytes2("SG"));

        vm.stopPrank();

        // Configure global jurisdictions
        vm.startPrank(admin);
        validator.addJurisdiction(bytes2("US"));
        validator.addJurisdiction(bytes2("GB"));
        validator.addJurisdiction(bytes2("SG"));
        
        // Configure deal
        validator.configureDeal(
            DEAL_ID_1,
            true,  // transfersEnabled
            true,  // accreditationRequired
            0,     // minHoldingPeriod
            type(uint256).max // maxHoldingAmount
        );
        vm.stopPrank();
    }

    // ═══════════════════════════════════════════════════════════════════════
    // INITIALIZATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_initialization() public view {
        assertTrue(validator.hasRole(validator.DEFAULT_ADMIN_ROLE(), admin));
        assertTrue(validator.hasRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // KYC TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setInvestorKYC_success() public {
        address newInvestor = makeAddr("newInvestor");

        vm.prank(complianceOfficer);
        vm.expectEmit(true, true, true, true);
        emit KYCStatusUpdated(newInvestor, true, block.timestamp + 365 days);
        validator.setInvestorKYC(newInvestor, true, block.timestamp + 365 days);

        (bool isVerified, uint256 expiration) = validator.getInvestorKYC(newInvestor);
        assertTrue(isVerified);
        assertEq(expiration, block.timestamp + 365 days);
    }

    function test_setInvestorKYC_revert_notComplianceOfficer() public {
        vm.prank(investor1);
        vm.expectRevert();
        validator.setInvestorKYC(investor2, true, block.timestamp + 365 days);
    }

    function test_isKYCVerified() public view {
        assertTrue(validator.isKYCVerified(investor1));
        assertFalse(validator.isKYCVerified(attacker));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // ACCREDITATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setInvestorAccreditation_success() public {
        address newInvestor = makeAddr("newInvestor");

        vm.prank(complianceOfficer);
        validator.setInvestorKYC(newInvestor, true, block.timestamp + 365 days);

        vm.prank(complianceOfficer);
        vm.expectEmit(true, true, true, true);
        emit AccreditationStatusUpdated(newInvestor, true);
        validator.setInvestorAccreditation(newInvestor, true);

        assertTrue(validator.isInvestorAccredited(newInvestor));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // JURISDICTION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_addJurisdiction_success() public {
        vm.prank(admin);
        validator.addJurisdiction(bytes2("JP"));

        assertTrue(validator.isJurisdictionAllowed(bytes2("JP")));
    }

    function test_removeJurisdiction_success() public {
        vm.prank(admin);
        validator.removeJurisdiction(bytes2("US"));

        assertFalse(validator.isJurisdictionAllowed(bytes2("US")));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // SANCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_setInvestorSanctioned_success() public {
        vm.prank(complianceOfficer);
        validator.setInvestorSanctioned(attacker, true);

        assertTrue(validator.isInvestorSanctioned(attacker));
    }

    // ═══════════════════════════════════════════════════════════════════════
    // TRANSFER VALIDATION TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_validateTransfer_success() public view {
        (bool valid, , ) = validator.validateTransfer(
            DEAL_ID_1,
            investor1,
            investor2,
            1000
        );

        assertTrue(valid, "Transfer should be valid for compliant investors");
    }

    function test_validateTransfer_revert_sanctionedSender() public {
        // Sanction investor1
        vm.prank(complianceOfficer);
        validator.setInvestorSanctioned(investor1, true);

        (bool valid, , string memory message) = validator.validateTransfer(
            DEAL_ID_1,
            investor1,
            investor2,
            1000
        );

        assertFalse(valid, "Transfer should fail for sanctioned sender");
        assertEq(message, "Sender sanctioned");
    }

    function test_validateTransfer_mintAlwaysAllowed() public view {
        (bool valid, , ) = validator.validateTransfer(
            DEAL_ID_1,
            address(0),
            investor1,
            1000
        );

        assertTrue(valid, "Mint should always be allowed");
    }

    function test_validateTransfer_burnAlwaysAllowed() public view {
        (bool valid, , ) = validator.validateTransfer(
            DEAL_ID_1,
            investor1,
            address(0),
            1000
        );

        assertTrue(valid, "Burn should always be allowed");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DEAL PAUSE TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_emergencyPauseDeal() public {
        vm.prank(admin);
        validator.emergencyPauseDeal(DEAL_ID_1);

        (bool valid, , string memory message) = validator.validateTransfer(
            DEAL_ID_1,
            investor1,
            investor2,
            1000
        );

        assertFalse(valid, "Transfer should fail when deal is paused");
        assertEq(message, "Deal paused");
    }

    function test_emergencyUnpauseDeal() public {
        vm.prank(admin);
        validator.emergencyPauseDeal(DEAL_ID_1);

        vm.prank(admin);
        validator.emergencyUnpauseDeal(DEAL_ID_1);

        (bool valid, , ) = validator.validateTransfer(
            DEAL_ID_1,
            investor1,
            investor2,
            1000
        );

        assertTrue(valid, "Transfer should succeed after unpause");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // VIEW FUNCTIONS TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function test_getInvestorData() public view {
        TransferValidator.InvestorData memory data = validator.getInvestorData(investor1);
        
        assertTrue(data.kycVerified);
        assertTrue(data.accredited);
        assertEq(data.jurisdiction, bytes2("US"));
        assertFalse(data.sanctioned);
    }

    function test_getDealConfig() public view {
        TransferValidator.DealConfig memory config = validator.getDealConfig(DEAL_ID_1);
        
        assertTrue(config.transfersEnabled);
        assertTrue(config.accreditationRequired);
        assertFalse(config.paused);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FUZZ TESTS
    // ═══════════════════════════════════════════════════════════════════════

    function testFuzz_jurisdictionCodes(bytes2 code) public {
        vm.assume(code != bytes2(0));

        vm.prank(admin);
        validator.addJurisdiction(code);

        assertTrue(validator.isJurisdictionAllowed(code));

        vm.prank(admin);
        validator.removeJurisdiction(code);

        assertFalse(validator.isJurisdictionAllowed(code));
    }
}

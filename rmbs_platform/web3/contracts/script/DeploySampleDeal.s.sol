// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {TrancheFactory} from "../src/tokens/TrancheFactory.sol";
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {WaterfallEngine} from "../src/waterfall/WaterfallEngine.sol";
import {ServicerOracle} from "../src/oracle/ServicerOracle.sol";

/**
 * @title DeploySampleDeal
 * @notice Script to deploy a sample RMBS deal with 3 tranches
 * @dev Run this after Deploy.s.sol
 * 
 * Usage:
 *   forge script script/DeploySampleDeal.s.sol:DeploySampleDeal \
 *     --rpc-url <RPC_URL> --broadcast
 * 
 * Environment Variables Required:
 *   - DEPLOYER_PRIVATE_KEY: Private key for deployment
 *   - FACTORY_ADDRESS: TrancheFactory proxy address
 *   - VALIDATOR_ADDRESS: TransferValidator proxy address
 *   - WATERFALL_ADDRESS: WaterfallEngine proxy address
 *   - ORACLE_ADDRESS: ServicerOracle proxy address
 *   - PAYMENT_TOKEN_ADDRESS: USDC or other ERC20 for payments
 *   - TRUSTEE_ADDRESS: Trustee address for the deal
 *   - SERVICER_ADDRESS: Servicer address for the deal
 */
contract DeploySampleDeal is Script {
    // Contract addresses (from environment)
    TrancheFactory public factory;
    TransferValidator public validator;
    WaterfallEngine public waterfall;
    ServicerOracle public oracle;
    address public paymentToken;
    address public trustee;
    address public servicer;
    
    // Deal parameters
    bytes32 public constant DEAL_ID = keccak256("SAMPLE_DEAL_2026_1");
    string public constant DEAL_NAME = "Sample RMBS Deal 2026-1";
    
    // Tranche addresses (will be populated after deployment)
    address public seniorTranche;
    address public mezzTranche;
    address public juniorTranche;
    
    function setUp() public {
        factory = TrancheFactory(vm.envAddress("FACTORY_ADDRESS"));
        validator = TransferValidator(vm.envAddress("VALIDATOR_ADDRESS"));
        waterfall = WaterfallEngine(vm.envAddress("WATERFALL_ADDRESS"));
        oracle = ServicerOracle(vm.envAddress("ORACLE_ADDRESS"));
        paymentToken = vm.envAddress("PAYMENT_TOKEN_ADDRESS");
        trustee = vm.envOr("TRUSTEE_ADDRESS", msg.sender);
        servicer = vm.envOr("SERVICER_ADDRESS", msg.sender);
        
        console2.log("=== Sample Deal Deployment ===");
        console2.log("Factory:", address(factory));
        console2.log("Validator:", address(validator));
        console2.log("Waterfall:", address(waterfall));
        console2.log("Oracle:", address(oracle));
        console2.log("Payment Token:", paymentToken);
        console2.log("Trustee:", trustee);
        console2.log("Servicer:", servicer);
        console2.log("");
    }
    
    function run() public {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        vm.startBroadcast(deployerPrivateKey);
        
        // Step 1: Register the deal
        console2.log("Step 1: Registering deal...");
        _registerDeal();
        
        // Step 2: Configure compliance rules
        console2.log("\nStep 2: Configuring compliance rules...");
        _configureCompliance();
        
        // Step 3: Deploy tranches
        console2.log("\nStep 3: Deploying tranches...");
        _deployTranches();
        
        // Step 4: Setup waterfall
        console2.log("\nStep 4: Setting up waterfall...");
        _setupWaterfall();
        
        // Step 5: Authorize servicer
        console2.log("\nStep 5: Authorizing servicer...");
        _authorizeServicer();
        
        vm.stopBroadcast();
        
        // Print summary
        console2.log("\n=== Deal Deployment Complete ===");
        _printSummary();
    }
    
    function _registerDeal() internal {
        uint256 closingDate = block.timestamp;
        uint256 maturityDate = block.timestamp + (5 * 365 days); // 5 years
        
        factory.registerDeal(
            DEAL_ID,
            DEAL_NAME,
            closingDate,
            maturityDate
        );
        
        console2.log("Deal registered with ID:", vm.toString(DEAL_ID));
    }
    
    function _configureCompliance() internal {
        // Configure deal-specific compliance rules
        validator.configureDeal(
            DEAL_ID,
            true,  // transfersEnabled
            false, // accreditationRequired (set to true for Reg D)
            0,     // minHoldingPeriod
            0      // maxHoldingAmount (0 = no limit)
        );
        
        // Add allowed jurisdictions (US already added in main deployment)
        // Add more if needed: GB, CA, EU, etc.
        
        console2.log("Compliance rules configured");
    }
    
    function _deployTranches() internal {
        uint256 maturityDate = block.timestamp + (3 * 365 days); // 3 years
        
        // Create array of tranche parameters
        RMBSTranche.InitParams[] memory paramsArray = new RMBSTranche.InitParams[](3);
        
        // Senior Tranche (Class A) - 70% of capital structure
        paramsArray[0] = RMBSTranche.InitParams({
            dealId: DEAL_ID,
            trancheId: "A",
            name: "Sample RMBS 2026-1 Class A",
            symbol: "RMBS26-A",
            originalFaceValue: 70_000_000e18,  // $70M
            couponRateBps: 400,                 // 4.00%
            paymentFrequency: 12,               // Monthly
            maturityDate: maturityDate,
            paymentToken: paymentToken,
            transferValidator: address(validator),
            admin: msg.sender,
            issuer: msg.sender,
            trustee: trustee
        });
        
        // Mezzanine Tranche (Class M) - 20% of capital structure
        paramsArray[1] = RMBSTranche.InitParams({
            dealId: DEAL_ID,
            trancheId: "M",
            name: "Sample RMBS 2026-1 Class M",
            symbol: "RMBS26-M",
            originalFaceValue: 20_000_000e18,  // $20M
            couponRateBps: 650,                 // 6.50%
            paymentFrequency: 12,               // Monthly
            maturityDate: maturityDate,
            paymentToken: paymentToken,
            transferValidator: address(validator),
            admin: msg.sender,
            issuer: msg.sender,
            trustee: trustee
        });
        
        // Junior Tranche (Class B) - 10% of capital structure
        paramsArray[2] = RMBSTranche.InitParams({
            dealId: DEAL_ID,
            trancheId: "B",
            name: "Sample RMBS 2026-1 Class B",
            symbol: "RMBS26-B",
            originalFaceValue: 10_000_000e18,  // $10M
            couponRateBps: 950,                 // 9.50%
            paymentFrequency: 12,               // Monthly
            maturityDate: maturityDate,
            paymentToken: paymentToken,
            transferValidator: address(validator),
            admin: msg.sender,
            issuer: msg.sender,
            trustee: trustee
        });
        
        // Deploy all tranches in one transaction
        address[] memory trancheAddresses = factory.deployTranches(paramsArray);
        
        seniorTranche = trancheAddresses[0];
        mezzTranche = trancheAddresses[1];
        juniorTranche = trancheAddresses[2];
        
        console2.log("Senior Tranche (A):", seniorTranche);
        console2.log("Mezz Tranche (M):", mezzTranche);
        console2.log("Junior Tranche (B):", juniorTranche);
    }
    
    function _setupWaterfall() internal {
        // Create array of tranche addresses (senior to junior)
        address[] memory tranches = new address[](3);
        tranches[0] = seniorTranche;
        tranches[1] = mezzTranche;
        tranches[2] = juniorTranche;
        
        // Initialize waterfall with SEQUENTIAL principal paydown strategy
        waterfall.initializeDealWaterfall(
            DEAL_ID,
            paymentToken,
            tranches,
            WaterfallEngine.PrincipalPaydownStrategy.SEQUENTIAL,
            30,     // 0.30% trustee fee
            20,     // 0.20% servicer fee
            servicer
        );
        
        console2.log("Waterfall configured with SEQUENTIAL strategy");
    }
    
    function _authorizeServicer() internal {
        // Authorize servicer to submit loan tape data
        oracle.addAuthorizedServicer(DEAL_ID, servicer);
        
        console2.log("Servicer authorized:", servicer);
    }
    
    function _printSummary() internal view {
        console2.log("\n=== Deal Summary ===");
        console2.log("Deal ID:", vm.toString(DEAL_ID));
        console2.log("Deal Name:", DEAL_NAME);
        console2.log("");
        console2.log("Total Face Value: $100,000,000");
        console2.log("");
        console2.log("Tranches:");
        console2.log("  Class A (Senior):   $70M @ 4.00% -", seniorTranche);
        console2.log("  Class M (Mezz):     $20M @ 6.50% -", mezzTranche);
        console2.log("  Class B (Junior):   $10M @ 9.50% -", juniorTranche);
        console2.log("");
        console2.log("=== Next Steps ===");
        console2.log("1. Issue tokens to investors via RMBSTranche.issue()");
        console2.log("2. Setup KYC for investors via TransferValidator");
        console2.log("3. Servicer submits loan tape via ServicerOracle");
        console2.log("4. Trustee runs waterfall via WaterfallEngine");
        console2.log("5. Investors claim yield via RMBSTranche.claimYield()");
    }
}

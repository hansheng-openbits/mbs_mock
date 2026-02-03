// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Script, console2} from "forge-std/Script.sol";
import {ERC1967Proxy} from "@openzeppelin/contracts/proxy/ERC1967/ERC1967Proxy.sol";

// Core contracts
import {RMBSTranche} from "../src/tokens/RMBSTranche.sol";
import {TransferValidator} from "../src/compliance/TransferValidator.sol";
import {TrancheFactory} from "../src/tokens/TrancheFactory.sol";
import {WaterfallEngine} from "../src/waterfall/WaterfallEngine.sol";
import {ServicerOracle} from "../src/oracle/ServicerOracle.sol";
import {RoleRegistry} from "../src/access/RoleRegistry.sol";

/**
 * @title Deploy
 * @notice Main deployment script for RMBS Platform
 * @dev Deploys all core contracts with UUPS proxies
 * 
 * Usage:
 *   forge script script/Deploy.s.sol:Deploy --rpc-url <RPC_URL> --broadcast --verify
 * 
 * Environment Variables Required:
 *   - DEPLOYER_PRIVATE_KEY: Private key for deployment
 *   - ADMIN_ADDRESS: Platform admin address
 *   - COMPLIANCE_OFFICER_ADDRESS: Compliance officer address
 *   - ARBISCAN_API_KEY: For contract verification (optional)
 */
contract Deploy is Script {
    // Deployment addresses
    address public admin;
    address public complianceOfficer;
    
    // Implementation contracts
    RMBSTranche public trancheImpl;
    TransferValidator public validatorImpl;
    TrancheFactory public factoryImpl;
    WaterfallEngine public waterfallImpl;
    ServicerOracle public oracleImpl;
    RoleRegistry public roleRegistryImpl;
    
    // Proxy contracts
    TransferValidator public validator;
    TrancheFactory public factory;
    WaterfallEngine public waterfall;
    ServicerOracle public oracle;
    RoleRegistry public roleRegistry;
    
    function setUp() public {
        // Load addresses from environment or use defaults
        admin = vm.envOr("ADMIN_ADDRESS", msg.sender);
        complianceOfficer = vm.envOr("COMPLIANCE_OFFICER_ADDRESS", msg.sender);
        
        console2.log("=== RMBS Platform Deployment ===");
        console2.log("Deployer:", msg.sender);
        console2.log("Admin:", admin);
        console2.log("Compliance Officer:", complianceOfficer);
        console2.log("");
    }
    
    function run() public {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        vm.startBroadcast(deployerPrivateKey);
        
        // Step 1: Deploy implementation contracts
        console2.log("Step 1: Deploying implementation contracts...");
        _deployImplementations();
        
        // Step 2: Deploy and initialize proxies
        console2.log("\nStep 2: Deploying and initializing proxies...");
        _deployProxies();
        
        // Step 3: Setup roles and permissions
        console2.log("\nStep 3: Setting up roles and permissions...");
        _setupRoles();
        
        // Step 4: Link contracts
        console2.log("\nStep 4: Linking contracts...");
        _linkContracts();
        
        vm.stopBroadcast();
        
        // Step 5: Print deployment summary
        console2.log("\n=== Deployment Complete ===");
        _printSummary();
    }
    
    function _deployImplementations() internal {
        trancheImpl = new RMBSTranche();
        console2.log("RMBSTranche Implementation:", address(trancheImpl));
        
        validatorImpl = new TransferValidator();
        console2.log("TransferValidator Implementation:", address(validatorImpl));
        
        factoryImpl = new TrancheFactory();
        console2.log("TrancheFactory Implementation:", address(factoryImpl));
        
        waterfallImpl = new WaterfallEngine();
        console2.log("WaterfallEngine Implementation:", address(waterfallImpl));
        
        oracleImpl = new ServicerOracle();
        console2.log("ServicerOracle Implementation:", address(oracleImpl));
        
        roleRegistryImpl = new RoleRegistry();
        console2.log("RoleRegistry Implementation:", address(roleRegistryImpl));
    }
    
    function _deployProxies() internal {
        // Deploy RoleRegistry first (needed by other contracts)
        bytes memory roleRegistryInitData = abi.encodeWithSelector(
            RoleRegistry.initialize.selector,
            admin
        );
        address roleRegistryProxy = address(new ERC1967Proxy(address(roleRegistryImpl), roleRegistryInitData));
        roleRegistry = RoleRegistry(roleRegistryProxy);
        console2.log("RoleRegistry Proxy:", address(roleRegistry));
        
        // Deploy ServicerOracle (initialize with zero address for WaterfallEngine, will set later)
        bytes memory oracleInitData = abi.encodeWithSelector(
            ServicerOracle.initialize.selector,
            admin,
            address(0) // Temporary, will be set after WaterfallEngine deployment
        );
        address oracleProxy = address(new ERC1967Proxy(address(oracleImpl), oracleInitData));
        oracle = ServicerOracle(oracleProxy);
        console2.log("ServicerOracle Proxy:", address(oracle));
        
        // Deploy TransferValidator
        bytes memory validatorInitData = abi.encodeWithSelector(
            TransferValidator.initialize.selector,
            admin,
            complianceOfficer
        );
        address validatorProxy = address(new ERC1967Proxy(address(validatorImpl), validatorInitData));
        validator = TransferValidator(validatorProxy);
        console2.log("TransferValidator Proxy:", address(validator));
        
        // Deploy TrancheFactory
        bytes memory factoryInitData = abi.encodeWithSelector(
            TrancheFactory.initialize.selector,
            admin,
            address(trancheImpl),
            address(validator)
        );
        address factoryProxy = address(new ERC1967Proxy(address(factoryImpl), factoryInitData));
        factory = TrancheFactory(factoryProxy);
        console2.log("TrancheFactory Proxy:", address(factory));
        
        // Deploy WaterfallEngine
        bytes memory waterfallInitData = abi.encodeWithSelector(
            WaterfallEngine.initialize.selector,
            admin,
            address(roleRegistry),
            address(oracle)
        );
        address waterfallProxy = address(new ERC1967Proxy(address(waterfallImpl), waterfallInitData));
        waterfall = WaterfallEngine(waterfallProxy);
        console2.log("WaterfallEngine Proxy:", address(waterfall));
    }
    
    function _setupRoles() internal {
        // Grant roles in RoleRegistry
        // Note: Deal-specific roles will be granted when deals are created
        
        // Grant compliance officer role in TransferValidator
        validator.grantRole(validator.COMPLIANCE_OFFICER_ROLE(), complianceOfficer);
        console2.log("Granted COMPLIANCE_OFFICER_ROLE to:", complianceOfficer);
        
        // Add US as allowed jurisdiction (default)
        validator.addJurisdiction(bytes2("US"));
        console2.log("Added jurisdiction: US");
    }
    
    function _linkContracts() internal {
        // Link ServicerOracle to WaterfallEngine (now that both are deployed)
        oracle.setWaterfallEngine(address(waterfall));
        console2.log("Linked ServicerOracle to WaterfallEngine");
        console2.log("All contracts linked successfully");
    }
    
    function _printSummary() internal view {
        console2.log("\n=== Implementation Contracts ===");
        console2.log("RMBSTranche:", address(trancheImpl));
        console2.log("TransferValidator:", address(validatorImpl));
        console2.log("TrancheFactory:", address(factoryImpl));
        console2.log("WaterfallEngine:", address(waterfallImpl));
        console2.log("ServicerOracle:", address(oracleImpl));
        console2.log("RoleRegistry:", address(roleRegistryImpl));
        
        console2.log("\n=== Proxy Contracts (Use These) ===");
        console2.log("RoleRegistry:", address(roleRegistry));
        console2.log("ServicerOracle:", address(oracle));
        console2.log("TransferValidator:", address(validator));
        console2.log("TrancheFactory:", address(factory));
        console2.log("WaterfallEngine:", address(waterfall));
        
        console2.log("\n=== Roles ===");
        console2.log("Admin:", admin);
        console2.log("Compliance Officer:", complianceOfficer);
        
        console2.log("\n=== Next Steps ===");
        console2.log("1. Verify contracts on Arbiscan");
        console2.log("2. Add additional jurisdictions via TransferValidator");
        console2.log("3. Register your first deal via TrancheFactory");
        console2.log("4. Deploy tranches for your deal");
        console2.log("5. Setup waterfall configuration");
    }
}

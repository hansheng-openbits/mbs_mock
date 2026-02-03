#!/bin/bash

# Monitor for Arbitrum Sepolia testnet ETH and automatically deploy
# Usage: ./monitor_and_deploy_testnet.sh

set -e

export PATH="$HOME/.foundry/bin:$PATH"

ADDRESS="0x54d353CFA012F1E0D848F23d42755e98995Dc5f2"
RPC_URL="https://sepolia-rollup.arbitrum.io/rpc"
REQUIRED_BALANCE="0.001"  # Minimum 0.001 ETH required
PRIVATE_KEY="0xbbfdb21e03be99cbf8089aacb700d2745d0f0325ee114383a5b45f73214023b7"

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     ARBITRUM SEPOLIA TESTNET - DEPLOYMENT MONITOR              ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Address: $ADDRESS"
echo "🌐 Network: Arbitrum Sepolia (Testnet)"
echo "💰 Required: $REQUIRED_BALANCE ETH minimum"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📖 To get testnet ETH, see: GET_TESTNET_ETH_GUIDE.md"
echo ""
echo "🎯 RECOMMENDED: Join Arbitrum Discord"
echo "   https://discord.gg/arbitrum"
echo "   Command: /faucet $ADDRESS"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Monitoring for testnet ETH... (checking every 10 seconds)"
echo ""

# Monitor for 30 minutes (180 checks)
for i in {1..180}; do
    BALANCE=$(cast balance $ADDRESS --rpc-url $RPC_URL --ether 2>/dev/null || echo "0")
    
    # Calculate elapsed time
    ELAPSED=$((i * 10))
    MINUTES=$((ELAPSED / 60))
    SECONDS=$((ELAPSED % 60))
    
    printf "[%3d/180] Time: %02d:%02d | Balance: %s ETH\r" $i $MINUTES $SECONDS "$BALANCE"
    
    # Check if balance is greater than 0
    if [[ "$BALANCE" != "0.000000000000000000" ]] && [[ "$BALANCE" != "0" ]]; then
        echo ""
        echo ""
        echo "✅ TESTNET ETH DETECTED: $BALANCE ETH on Arbitrum Sepolia!"
        echo ""
        
        # Check if balance is sufficient
        BALANCE_CHECK=$(echo "$BALANCE >= $REQUIRED_BALANCE" | bc -l 2>/dev/null || echo "0")
        
        if [[ "$BALANCE_CHECK" == "1" ]]; then
            echo "💰 Balance sufficient for deployment!"
            echo ""
            echo "🚀 Starting testnet deployment in 3 seconds..."
            sleep 3
            echo ""
            echo "═══════════════════════════════════════════════════════════════"
            echo "  DEPLOYING TO ARBITRUM SEPOLIA (TESTNET)"
            echo "═══════════════════════════════════════════════════════════════"
            echo ""
            
            # Set environment variables
            export DEPLOYER_PRIVATE_KEY="$PRIVATE_KEY"
            export ADMIN_ADDRESS="$ADDRESS"
            export COMPLIANCE_OFFICER_ADDRESS="$ADDRESS"
            
            # Run deployment
            forge script script/Deploy.s.sol:Deploy \
                --rpc-url $RPC_URL \
                --broadcast \
                -vv
            
            EXIT_CODE=$?
            
            if [ $EXIT_CODE -eq 0 ]; then
                echo ""
                echo "═══════════════════════════════════════════════════════════════"
                echo "  ✅ TESTNET DEPLOYMENT SUCCESSFUL!"
                echo "═══════════════════════════════════════════════════════════════"
                echo ""
                echo "📝 Deployment details saved to:"
                echo "   broadcast/Deploy.s.sol/421614/run-latest.json"
                echo ""
                echo "🔍 View on Arbiscan Testnet:"
                echo "   https://sepolia.arbiscan.io/address/$ADDRESS"
                echo ""
                echo "📊 You now have contracts deployed on:"
                echo "   ✅ Arbitrum One (Mainnet) - Production"
                echo "   ✅ Arbitrum Sepolia (Testnet) - Testing"
                echo ""
                
                # Check remaining balance
                REMAINING=$(cast balance $ADDRESS --rpc-url $RPC_URL --ether 2>/dev/null || echo "0")
                echo "💰 Remaining testnet balance: $REMAINING ETH"
                echo ""
                
                # Create comparison document
                echo "Creating deployment comparison..."
                cat > TESTNET_VS_MAINNET.md << 'COMPARISON_EOF'
# Testnet vs Mainnet Deployment Comparison

## Overview

You now have RMBS Platform deployed on both networks for different purposes.

---

## Network Comparison

| Aspect | Mainnet (Arbitrum One) | Testnet (Arbitrum Sepolia) |
|--------|------------------------|----------------------------|
| **Purpose** | Production use | Testing & development |
| **Chain ID** | 42161 | 421614 |
| **ETH Type** | Real money | Free testnet ETH |
| **Explorer** | https://arbiscan.io/ | https://sepolia.arbiscan.io/ |
| **Cost** | ~$3.85 spent | FREE |
| **Status** | ✅ Live | ✅ Live |

---

## When to Use Each

### Use MAINNET for:
- ✅ Production deployments
- ✅ Real financial transactions
- ✅ Public-facing features
- ✅ Audited and tested code only

### Use TESTNET for:
- ✅ Development and testing
- ✅ Integration testing
- ✅ User acceptance testing (UAT)
- ✅ Experimenting with new features
- ✅ Training and documentation

---

## Contract Addresses

See:
- **Mainnet**: DEPLOYMENT_SUMMARY.md
- **Testnet**: broadcast/Deploy.s.sol/421614/run-latest.json

---

## Best Practices

1. **Always test on testnet first** before deploying changes to mainnet
2. **Keep both deployments in sync** - same configuration
3. **Use testnet for demos** - no real money at risk
4. **Monitor both networks** - set up alerts
5. **Document changes** - maintain change log for both

---

## Testing Workflow

```
1. Develop locally
   ↓
2. Test on Arbitrum Sepolia (testnet)
   ↓
3. UAT and security review
   ↓
4. Deploy to Arbitrum One (mainnet)
   ↓
5. Monitor and maintain
```

---

## 🎉 Congratulations!

You now have a complete dual-deployment setup:
- Production-ready contracts on mainnet
- Safe testing environment on testnet

Ready for serious RMBS platform development! 🚀
COMPARISON_EOF
                
                echo "✅ Created TESTNET_VS_MAINNET.md"
                echo ""
                echo "🎉 All done! You're ready to test safely on testnet!"
                echo ""
                
            else
                echo ""
                echo "❌ Testnet deployment failed with exit code $EXIT_CODE"
                echo "💡 Check the logs above for details"
                echo ""
                echo "Common issues:"
                echo "  • Insufficient testnet ETH (need ~0.002 ETH)"
                echo "  • RPC connection issues"
                echo "  • Contract compilation errors"
                echo ""
                echo "Try running manually:"
                echo "  forge script script/Deploy.s.sol:Deploy \\"
                echo "    --rpc-url $RPC_URL \\"
                echo "    --broadcast -vvv"
                echo ""
                exit $EXIT_CODE
            fi
            
            exit 0
        else
            echo "⚠️  Balance ($BALANCE ETH) is less than required ($REQUIRED_BALANCE ETH)"
            echo "💡 Please get at least $REQUIRED_BALANCE ETH to continue"
            echo ""
            echo "Quick options:"
            echo "  1. Arbitrum Discord: https://discord.gg/arbitrum"
            echo "  2. pk910 PoW Faucet: https://arbitrum-sepolia-faucet.pk910.de/"
            echo ""
            exit 1
        fi
    fi
    
    sleep 10
done

echo ""
echo ""
echo "⏰ Monitoring complete. No testnet ETH detected after 30 minutes."
echo ""
FINAL=$(cast balance $ADDRESS --rpc-url $RPC_URL --ether 2>/dev/null || echo "0")
echo "Current balance: $FINAL ETH"
echo "Required balance: $REQUIRED_BALANCE ETH"
echo ""
echo "💡 TO GET TESTNET ETH:"
echo ""
echo "🥇 BEST: Arbitrum Discord Faucet"
echo "   1. Join: https://discord.gg/arbitrum"
echo "   2. Go to #sepolia-faucet channel"
echo "   3. Type: /faucet $ADDRESS"
echo "   4. Get 0.01-0.1 ETH instantly!"
echo ""
echo "🥈 ALTERNATIVE: pk910 PoW Faucet"
echo "   1. Visit: https://arbitrum-sepolia-faucet.pk910.de/"
echo "   2. Enter address and start mining"
echo "   3. Mine for 10-30 minutes"
echo "   4. Claim your testnet ETH"
echo ""
echo "📖 Full guide: cat GET_TESTNET_ETH_GUIDE.md"
echo ""
echo "After getting ETH, run this script again:"
echo "  ./monitor_and_deploy_testnet.sh"
echo ""

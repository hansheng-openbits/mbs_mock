#!/bin/bash

# Deploy to Arbitrum One (Production)
# This script will monitor for ETH and automatically deploy to Arbitrum One mainnet

set -e

export PATH="$HOME/.foundry/bin:$PATH"

ADDRESS="0x54d353CFA012F1E0D848F23d42755e98995Dc5f2"
RPC_URL="https://arb1.arbitrum.io/rpc"
REQUIRED_BALANCE="0.002" # Minimum 0.002 ETH required

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║     ARBITRUM ONE (MAINNET) DEPLOYMENT MONITOR                  ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Address: $ADDRESS"
echo "🌐 Network: Arbitrum One (Production)"
echo "💰 Required: $REQUIRED_BALANCE ETH minimum"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "⏰ Monitoring for ETH... (checking every 10 seconds)"
echo ""

# Monitor for 10 minutes
for i in {1..60}; do
    BALANCE=$(cast balance $ADDRESS --rpc-url $RPC_URL --ether 2>/dev/null || echo "0")
    
    printf "[Check %2d/60] Balance: %s ETH\r" $i "$BALANCE"
    
    # Check if balance is greater than 0
    if [[ "$BALANCE" != "0.000000000000000000" ]] && [[ "$BALANCE" != "0" ]]; then
        echo ""
        echo ""
        echo "✅ ETH DETECTED: $BALANCE ETH on Arbitrum One"
        echo ""
        
        # Check if balance is sufficient
        BALANCE_CHECK=$(echo "$BALANCE >= $REQUIRED_BALANCE" | bc -l 2>/dev/null || echo "0")
        
        if [[ "$BALANCE_CHECK" == "1" ]]; then
            echo "💰 Balance sufficient for deployment!"
            echo ""
            echo "🚀 Starting deployment to Arbitrum One in 3 seconds..."
            sleep 3
            echo ""
            echo "═══════════════════════════════════════════════════════════════"
            echo "  DEPLOYING TO ARBITRUM ONE (PRODUCTION MAINNET)"
            echo "═══════════════════════════════════════════════════════════════"
            echo ""
            
            # Run deployment
            forge script script/Deploy.s.sol:Deploy \
                --rpc-url $RPC_URL \
                --broadcast \
                --verify \
                -vvv
            
            EXIT_CODE=$?
            
            if [ $EXIT_CODE -eq 0 ]; then
                echo ""
                echo "═══════════════════════════════════════════════════════════════"
                echo "  ✅ DEPLOYMENT SUCCESSFUL!"
                echo "═══════════════════════════════════════════════════════════════"
                echo ""
                echo "📝 Deployment details saved to:"
                echo "   broadcast/Deploy.s.sol/42161/run-latest.json"
                echo ""
                echo "🔍 View on Arbiscan:"
                echo "   https://arbiscan.io/address/$ADDRESS"
                echo ""
            else
                echo ""
                echo "❌ Deployment failed with exit code $EXIT_CODE"
                echo "💡 Check the logs above for details"
                exit $EXIT_CODE
            fi
            
            exit 0
        else
            echo "⚠️  Balance ($BALANCE ETH) is less than required ($REQUIRED_BALANCE ETH)"
            echo "💡 Please send at least $REQUIRED_BALANCE ETH to continue"
            exit 1
        fi
    fi
    
    sleep 10
done

echo ""
echo ""
echo "⏰ Monitoring complete. No sufficient ETH detected after 10 minutes."
echo ""
echo "Current balance: $(cast balance $ADDRESS --rpc-url $RPC_URL --ether 2>/dev/null || echo '0') ETH"
echo "Required balance: $REQUIRED_BALANCE ETH"
echo ""
echo "💡 After sending ETH to Arbitrum One, run this script again:"
echo "   ./deploy_to_arbitrum_one.sh"
echo ""

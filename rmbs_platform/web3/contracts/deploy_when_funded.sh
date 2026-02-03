#!/bin/bash
set -e

ACCOUNT="0x54d353CFA012F1E0D848F23d42755e98995Dc5f2"
RPC="https://sepolia-rollup.arbitrum.io/rpc"
MIN_BALANCE="0.002" # Need at least 0.002 ETH for deployment

echo "╔══════════════════════════════════════════════════════════════════╗"
echo "║        RMBS Platform - Automated Testnet Deployment             ║"
echo "╚══════════════════════════════════════════════════════════════════╝"
echo ""
echo "📍 Monitoring address: $ACCOUNT"
echo "⏳ Waiting for testnet ETH..."
echo ""
echo "💡 Get testnet ETH from:"
echo "   🔗 https://faucet.quicknode.com/arbitrum/sepolia"
echo ""
echo "Press Ctrl+C to cancel"
echo ""

# Function to check balance
check_balance() {
    cast balance $ACCOUNT --rpc-url $RPC --ether 2>/dev/null || echo "0"
}

# Poll every 10 seconds
attempt=1
while true; do
    BALANCE=$(check_balance)
    
    echo "[$attempt] Current balance: $BALANCE ETH"
    
    # Check if balance is sufficient (using bc for floating point comparison)
    if command -v bc &> /dev/null; then
        IS_SUFFICIENT=$(echo "$BALANCE >= $MIN_BALANCE" | bc -l)
    else
        # Fallback: simple string comparison (works for most cases)
        if [[ "$BALANCE" != "0"* ]] && [[ "$BALANCE" != "0.000"* ]]; then
            IS_SUFFICIENT=1
        else
            IS_SUFFICIENT=0
        fi
    fi
    
    if [[ $IS_SUFFICIENT -eq 1 ]]; then
        echo ""
        echo "✅ Sufficient balance detected! ($BALANCE ETH)"
        echo ""
        echo "🚀 Starting deployment in 3 seconds..."
        sleep 3
        
        echo ""
        echo "═══════════════════════════════════════════════════════════════"
        echo "  DEPLOYING TO ARBITRUM SEPOLIA TESTNET"
        echo "═══════════════════════════════════════════════════════════════"
        echo ""
        
        # Run deployment
        forge script script/Deploy.s.sol:Deploy \
          --rpc-url $RPC \
          --broadcast \
          -vvv
        
        EXIT_CODE=$?
        
        if [ $EXIT_CODE -eq 0 ]; then
            echo ""
            echo "╔══════════════════════════════════════════════════════════════╗"
            echo "║              ✅ DEPLOYMENT SUCCESSFUL! ✅                     ║"
            echo "╚══════════════════════════════════════════════════════════════╝"
            echo ""
            echo "📁 Deployment details saved to:"
            echo "   broadcast/Deploy.s.sol/421614/run-latest.json"
            echo ""
            echo "🔍 View your contracts on Arbiscan:"
            echo "   https://sepolia.arbiscan.io/address/$ACCOUNT"
        else
            echo ""
            echo "❌ Deployment failed with exit code: $EXIT_CODE"
            echo "Check logs above for details"
        fi
        
        break
    fi
    
    sleep 10
    ((attempt++))
done

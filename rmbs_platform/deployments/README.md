# Deployments Directory

This directory contains **deployed contract addresses** per network.

## Structure

```
deployments/
├── localhost/          # Local development chain
│   └── contracts.json  # Deployed contract addresses
├── polygon/            # Polygon mainnet
│   └── contracts.json  # (empty until deployed)
└── mainnet/            # Ethereum mainnet
    └── contracts.json  # (empty until deployed)
```

## contracts.json Format

```json
{
  "deals": {
    "DEAL_ID": {
      "tranches": {
        "ClassA1": "0x...",
        "ClassA2": "0x..."
      },
      "loan_nft": "0x...",
      "updated_at": "ISO timestamp"
    }
  }
}
```

## Switching Networks

To switch networks, update `ACTIVE_NETWORK` in `api_main.py`:

```python
ACTIVE_NETWORK = "polygon"  # or "mainnet", "localhost"
```

## Deploying to a New Network

1. Configure `config/chains/{network}.json`
2. Deploy contracts using `web3/scripts/deploy.js`
3. Contract addresses will be saved to `deployments/{network}/contracts.json`

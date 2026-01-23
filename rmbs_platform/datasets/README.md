## Datasets (User-Friendly Deal Bundles)

This folder groups **all inputs for a deal** in one place so users can quickly find:
- **deal_spec** (deal structure / rules)
- **collateral** (pool snapshot + ML/tape references)
- **loan tape** (origination tape for ML / loan-level runs)
- **servicer tapes** (monthly performance remits)

### Folder layout

Each deal has its own folder:

```
datasets/<DEAL_ID>/
├── deal_spec.json        # Deal specification used by the engine/API
├── collateral.json       # Collateral JSON (upload-ready; pool stats + loan_data refs)
├── loan_tape.csv         # Optional: origination tape for ML / loan-level runs
├── servicer_tape.csv     # Optional: consolidated pool-level performance tape
└── servicer/             # Optional: monthly tapes (one file per period)
    ├── servicer_<period>.csv
    └── ...
```

### Automatic Synchronization

**Files in this folder are automatically synced** when you upload data via the API:
- Upload deal spec → synced to `datasets/{deal_id}/deal_spec.json`
- Upload collateral → synced to `datasets/{deal_id}/collateral.json`
- Upload loan tape → synced to `datasets/{deal_id}/loan_tape.csv`
- Upload performance → synced to `datasets/{deal_id}/servicer_tape.csv`

The API also persists data to primary storage folders (`deals/`, `collateral/`, `performance/`) and maintains version history in `*_versions/` folders. The `datasets/` folder provides a convenient single-location view of all deal data.

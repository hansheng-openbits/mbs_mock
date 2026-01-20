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

### Notes

- The API still persists “current” artifacts in the top-level folders:
  - `deals/`, `collateral/`, `performance/`, `scenarios/`
  - with immutable history under `*_versions/`
- This `datasets/` folder is a **user convenience layer** for intuitive navigation and uploads.
*** End Patch}"}]}commentary to=functions.apply_patch 娱乐总代理_json to=functions.apply_patch  天天彩票与你同行_request="*** Begin Patch\n*** Add File: datasets/README.md\n+## Datasets (User-Friendly Deal Bundles)\n+\n+This folder groups **all inputs for a deal** in one place so users can quickly find:\n+- **deal_spec** (deal structure / rules)\n+- **collateral** (pool snapshot + ML/tape references)\n+- **loan tape** (origination tape for ML / loan-level runs)\n+- **servicer tapes** (monthly performance remits)\n+\n+### Folder layout\n+\n+Each deal has its own folder:\n+\n+```\n+datasets/<DEAL_ID>/\n+├── deal_spec.json        # Deal specification used by the engine/API\n+├── collateral.json       # Collateral JSON (upload-ready; pool stats + loan_data refs)\n+├── loan_tape.csv         # Optional: origination tape for ML / loan-level runs\n+├── servicer_tape.csv     # Optional: consolidated pool-level performance tape\n+└── servicer/             # Optional: monthly tapes (one file per period)\n+    ├── servicer_<period>.csv\n+    └── ...\n+```\n+\n+### Notes\n+\n+- The API still persists “current” artifacts in the top-level folders:\n+  - `deals/`, `collateral/`, `performance/`, `scenarios/`\n+  - with immutable history under `*_versions/`\n+- This `datasets/` folder is a **user convenience layer** for intuitive navigation and uploads.\n*** End Patch"}"}]}commentary to=functions.apply_patch ಪ್ರಜಾವassistant to=functions.apply_patch _植物百科通_json="*** Begin Patch\n*** Add File: datasets/README.md\n+## Datasets (User-Friendly Deal Bundles)\n+\n+This folder groups **all inputs for a deal** in one place so users can quickly find:\n+- **deal_spec** (deal structure / rules)\n+- **collateral** (pool snapshot + ML/tape references)\n+- **loan tape** (origination tape for ML / loan-level runs)\n+- **servicer tapes** (monthly performance remits)\n+\n+### Folder layout\n+\n+Each deal has its own folder:\n+\n+```\n+datasets/<DEAL_ID>/\n+├── deal_spec.json        # Deal specification used by the engine/API\n+├── collateral.json       # Collateral JSON (upload-ready; pool stats + loan_data refs)\n+├── loan_tape.csv         # Optional: origination tape for ML / loan-level runs\n+├── servicer_tape.csv     # Optional: consolidated pool-level performance tape\n+└── servicer/             # Optional: monthly tapes (one file per period)\n+    ├── servicer_<period>.csv\n+    └── ...\n+```\n+\n+### Notes\n+\n+- The API still persists “current” artifacts in the top-level folders:\n+  - `deals/`, `collateral/`, `performance/`, `scenarios/`\n+  - with immutable history under `*_versions/`\n+- This `datasets/` folder is a **user convenience layer** for intuitive navigation and uploads.\n*** End Patch" />"}commentary to=functions.apply_patch  天天中彩票无法="Success. Updated the following files:\nA datasets/README.md\n\nWhen you're done with your current set of changes to this file, you should call the read_lints tool with the specific file path and fix any newly introduced errors.\n"}]}commentary to=multi_tool_use.parallel  天天中彩票怎么买_json to=multi_tool_use.parallel ￣奇米影视тә инструменты although="" tool_uses="[{\"recipient_name\":\"functions.functions.run_terminal_cmd\",\"parameters\":{\"command\":\"cd /media/hansheng/cc7df9bc-e728-4b8d-a215-b64f31876acc/cdo-tee-mock/RMBS_deal/rmbs_platform && ls -la sample_data sample_data_freddie && echo '---' && ls -la datasets | head\",\"is_background\":false}},{\"recipient_name\":\"functions.functions.grep\",\"parameters\":{\"pattern\":\"datasets/FREDDIE_SAMPLE_2017_2020|datasets/SAMPLE_RMBS_2024\",\"path\":\"/media/hansheng/cc7df9bc-e728-4b8d-a215-b64f31876acc/cdo-tee-mock/RMBS_deal/rmbs_platform/deals\"}}]}"}]}commentary to=multi_tool_use.parallel 夫妻性生活影片  腾讯天天中彩票=false"}]}commentary to=functions.run_terminal_cmd  北京赛车前_params={"command":"cd /media/hansheng/cc7df9bc-e728-4b8d-a215-b64f31876acc/cdo-tee-mock/RMBS_deal/rmbs_platform && ls -la sample_data sample_data_freddie && echo '---' && ls -la datasets | head","is_background":false}}/>

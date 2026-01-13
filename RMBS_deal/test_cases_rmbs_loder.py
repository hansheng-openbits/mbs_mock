import sys
import logging
from rmbs_loader import DealLoader, LogicIntegrityError, SchemaViolationError

# Configure logging to output to console
logging.basicConfig(
    level=logging.INFO, 
    format='[%(levelname)s] %(name)s: %(message)s',
    stream=sys.stdout
)

def run_demonstration():
    print("==================================================")
    print("      RMBS ENGINE: LOADER MODULE DEMO")
    print("==================================================\n")

    loader = DealLoader() # Initialize without external schema file for demo

    # --- SCENARIO 1: VALID DEAL ---
    print("--- Test Case 1: Loading Valid Deal ---")
    valid_payload = {
        "meta": {"deal_id": "RMBS_2024_A", "deal_name": "Goldman Sachs 2024-1", "asset_type": "NON_AGENCY_RMBS", "version": "1.0"},
        "dates": {"cutoff_date": "2024-01-01"}, # simplified
        "funds": [{"id": "IAF", "description": "Interest Available Funds"}],
        "accounts": [{"id": "RES", "type": "RESERVE"}],
        "variables": {"NetWAC": "0.055", "Delinq60": "0.02"},
        "bonds": [
            {
                "id": "A1", "type": "NOTE", "original_balance": 500000.0,
                "priority": {"interest": 1, "principal": 1},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.045, "variable_cap": "NetWAC"}
            }
        ],
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "1", "from_fund": "IAF", "action": "PAY_BOND_INTEREST", "group": "Senior"},
                    {"id": "2", "from_fund": "IAF", "action": "TRANSFER_FUND", "to": "RES"}
                ]
            }
        }
    }

    try:
        deal = loader.load_from_json(valid_payload)
        print(f"✅ SUCCESS: Loaded Deal '{deal.meta['deal_id']}'")
        print(f"   -> Bond A1 Balance: ${deal.bonds['A1'].original_balance:,.2f}")
        print(f"   -> Bond A1 Cap Ref: {deal.bonds['A1'].variable_cap_ref}")
    except Exception as e:
        print(f"❌ FAILED: {e}")

    # --- SCENARIO 2: LOGIC ERROR (Missing Variable) ---
    print("\n--- Test Case 2: Logic Integrity Violation ---")
    broken_logic_payload = valid_payload.copy()
    # INTRODUCING ERROR: Reference a variable 'OSCAR' that doesn't exist in 'variables'
    broken_logic_payload['bonds'] = [
        {
            "id": "B1", "type": "NOTE", "original_balance": 100.0,
            "priority": {"interest": 1, "principal": 1},
            "coupon": {"kind": "FIXED", "fixed_rate": 0.04, "variable_cap": "OSCAR"} 
        }
    ]

    try:
        loader.load_from_json(broken_logic_payload)
    except LogicIntegrityError as e:
        print("✅ CAUGHT EXPECTED LOGIC ERROR:")
        print(f"   Error Message: {e}")
    except Exception as e:
        print(f"❌ WRONG EXCEPTION CAUGHT: {type(e)}")

    # --- SCENARIO 3: SCHEMA/ENUM ERROR ---
    print("\n--- Test Case 3: Invalid Data Type ---")
    bad_enum_payload = valid_payload.copy()
    # INTRODUCING ERROR: 'FLOATING_SUPER' is not a valid CouponType Enum
    bad_enum_payload['bonds'] = [
        {
            "id": "C1", "type": "NOTE", "original_balance": 100.0,
            "priority": {"interest": 1, "principal": 1},
            "coupon": {"kind": "FLOATING_SUPER", "fixed_rate": 0.04} 
        }
    ]

    try:
        loader.load_from_json(bad_enum_payload)
    except SchemaViolationError as e:
        print("✅ CAUGHT EXPECTED SCHEMA ERROR:")
        print(f"   Error Message: {e}")
    except Exception as e:
         print(f"❌ WRONG EXCEPTION CAUGHT: {type(e)}")

if __name__ == "__main__":
    run_demonstration()
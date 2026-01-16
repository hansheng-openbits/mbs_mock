import traceback
from engine.loader import DealLoader
from engine.state import DealState
from engine.compute import ExpressionEngine

# The JSON causing the issue
json_spec = {
  "meta": {"deal_id": "DEBUG_TEST", "deal_name": "Debug", "asset_type": "RMBS", "version": "1.0"},
  "dates": {"cutoff_date": "2024-01-01", "closing_date": "2024-01-30", "first_payment_date": "2024-02-25", "maturity_date": "2054-01-01", "payment_frequency": "MONTHLY", "day_count": "30_360"},
  "collateral": {"original_balance": 1000.0, "loan_data": {}, "model_interface": {"kind": "LOAN_LEVEL_SIM", "inputs_required": []}},
  "funds": [{"id": "IAF", "description": "Interest"}],
  "accounts": [],
  "variables": {
    "DelinqTrigger": "tests.DelinqTest.failed"  # <--- The problematic rule
  },
  "tests": [
    {"id": "DelinqTest", "kind": "DELINQ", "calc": {"value_rule": "0"}, "threshold": {"rule": "0"}, "pass_if": "VALUE_LT_THRESHOLD", "effects": []}
  ],
  "bonds": [{"id": "A", "type": "NOTE", "original_balance": 1000, "priority": {"interest": 1, "principal": 1}, "coupon": {"kind": "FIXED"}}],
  "waterfalls": {"interest": {"steps": []}, "principal": {"steps": []}, "loss_allocation": {"loss_source_rule": "0", "write_down_order": []}}
}

print("--- STARTING DEBUG RUN ---")
try:
    # 1. Load
    print("1. Loading Deal...")
    loader = DealLoader('rmbs_platform/deal_spec.json')
    deal_def = loader.load_from_json(json_spec)
    
    # 2. Init State
    print("2. Initializing State...")
    state = DealState(deal_def)
    
    # 3. Check Flags
    print(f"   State Flags initialized as: {state.flags}")
    
    # 4. Compute
    print("3. Testing Compute Engine...")
    engine = ExpressionEngine()
    rule = "tests.DelinqTest.failed"
    result = engine.evaluate(rule, state)
    
    print(f"✅ SUCCESS! Rule '{rule}' evaluated to: {result}")

except Exception as e:
    print("\n❌ CRASH DETECTED!")
    traceback.print_exc()
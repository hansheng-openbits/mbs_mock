import logging
import math
from typing import Any, Dict
# Note: Import paths might vary based on your folder structure. 
# If running as a package, use: from .state import DealState, BondState
from .state import DealState, BondState

logger = logging.getLogger("RMBS.Compute")

class EvaluationError(Exception):
    pass

class ExpressionEngine:
    def __init__(self):
        self.safe_globals = {
            "__builtins__": None,
            "MIN": min,
            "MAX": max,
            "ABS": abs,
            "ROUND": round,
            "SUM": sum,
            "FLOOR": math.floor,
            "CEIL": math.ceil,
        }

    def evaluate(self, expression: str, state: DealState) -> Any:
        if expression is None or expression == "":
            return 0.0

        context = self._build_execution_context(state)

        try:
            # The context now includes a smart 'tests' object
            result = eval(expression, self.safe_globals, context)
            return result
        except NameError as e:
            logger.error(f"Rule failed: '{expression}'. Unknown variable: {e}")
            raise EvaluationError(f"Unknown variable in rule: {e}")
        except Exception as e:
            logger.error(f"Rule failed: '{expression}'. Error: {e}")
            raise EvaluationError(f"Calculation error: {e}")

    def evaluate_condition(self, rule: str, state: DealState) -> bool:
        if str(rule).lower() == "true": return True
        if str(rule).lower() == "false": return False
        result = self.evaluate(rule, state)
        return bool(result)

    def _build_execution_context(self, state: DealState) -> Dict[str, Any]:
        """
        Constructs the variable namespace, including the 'tests' proxy.
        """
        ctx = {}

        # 1. Fund Proxy
        class FundProxy:
            def __getattr__(self, key):
                return state.cash_balances.get(key, 0.0)
        
        ctx['funds'] = FundProxy()
        for fid, val in state.cash_balances.items():
            ctx[fid] = val

        # 2. Bond Proxy
        class BondWrapper:
            def __init__(self, b_state: BondState):
                self.balance = b_state.current_balance
                self.factor = b_state.factor
                self.shortfall = b_state.interest_shortfall
                self.original = b_state.original_balance

        class BondProxy:
            def __getattr__(self, key):
                if key in state.bonds:
                    return BondWrapper(state.bonds[key])
                return 0.0 
        
        ctx['bonds'] = BondProxy()

        # 3. Variables & Ledgers
        for name, val in state.variables.items():
            ctx[name] = val

        class LedgerProxy:
            def __getattr__(self, key):
                return state.ledgers.get(key, 0.0)
        ctx['ledgers'] = LedgerProxy()

        # 4. Collateral Proxy (for collateral.original_balance, etc.)
        class CollateralProxy:
            def __getattr__(self, key):
                return state.collateral.get(key, 0.0)
        ctx['collateral'] = CollateralProxy()

        # ---------------------------------------------------------
        # 5. NEW: Robust Tests Proxy
        # ---------------------------------------------------------
        
        # This handles the specific test ID (e.g., 'DelinqTest')
        class SingleTestWrapper:
            def __init__(self, test_id, flags):
                self.test_id = test_id
                self.flags = flags
            
            @property
            def failed(self):
                # Look up the specific ID in the flags dictionary.
                # Default to False (Pass) if the test hasn't run yet.
                return self.flags.get(self.test_id, False)

        # This handles the root 'tests' object
        class TestsProxy:
            def __getattr__(self, test_id):
                # Dynamically create a wrapper for WHATEVER ID the user typed
                return SingleTestWrapper(test_id, state.flags)
        
        ctx['tests'] = TestsProxy()
        # ---------------------------------------------------------

        return ctx
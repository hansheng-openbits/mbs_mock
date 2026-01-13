import logging
import math
from typing import Any, Dict, Optional, Union
from dataclasses import dataclass

# Import Module 2 State Logic
from rmbs_state import DealState, BondState

logger = logging.getLogger("RMBS.Compute")

class EvaluationError(Exception):
    """Raised when an expression cannot be computed."""
    pass

class ExpressionEngine:
    """
    Parses and executes logic strings against the DealState.
    """
    def __init__(self):
        # Define the 'built-ins' available inside the rules
        self.safe_globals = {
            "__builtins__": None,  # DISABLE all standard python builtins (safety)
            "MIN": min,
            "MAX": max,
            "ABS": abs,
            "ROUND": round,
            "SUM": sum,
            "FLOOR": math.floor,
            "CEIL": math.ceil,
        }

    def evaluate(self, expression: str, state: DealState) -> Any:
        """
        Main entry point. Evaluates a string rule.
        Returns: float (for amounts) or bool (for conditions).
        """
        if expression is None or expression == "":
            return 0.0

        # 1. Build the Context (The "Variables" available to the rule)
        # We flatten the state into a dictionary that the eval() engine understands.
        context = self._build_execution_context(state)

        # 2. Execute
        try:
            # We merge safe_globals (math functions) with context (deal data)
            result = eval(expression, self.safe_globals, context)
            return result
        except NameError as e:
            logger.error(f"Rule failed: '{expression}'. Unknown variable: {e}")
            raise EvaluationError(f"Unknown variable in rule: {e}")
        except Exception as e:
            logger.error(f"Rule failed: '{expression}'. Error: {e}")
            raise EvaluationError(f"Calculation error: {e}")

    def evaluate_condition(self, rule: str, state: DealState) -> bool:
        """Helper for boolean logic (Waterfalls, Triggers)."""
        # Shortcut: "true" string means always pass
        if str(rule).lower() == "true":
            return True
        if str(rule).lower() == "false":
            return False
            
        result = self.evaluate(rule, state)
        if not isinstance(result, bool):
             # Implicit conversion: 0.0 is False, >0 is True
             return bool(result)
        return result

    def _build_execution_context(self, state: DealState) -> Dict[str, Any]:
        """
        Constructs the namespace for the evaluator.
        Exposes:
          - 'funds.IAF'
          - 'bonds.A1.balance'
          - 'variables.NetWAC'
          - 'ledgers.PDL'
        """
        ctx = {}

        # A. Expose Funds and Accounts as 'funds.ID' and plain 'ID'
        # Usage: "funds.IAF" or just "IAF"
        class FundProxy:
            def __getitem__(self, key):
                return state.cash_balances.get(key, 0.0)
            def __getattr__(self, key):
                return state.cash_balances.get(key, 0.0)
        
        ctx['funds'] = FundProxy()
        # Also expose top-level IDs for convenience (e.g. "IAF > 0")
        for fid, val in state.cash_balances.items():
            ctx[fid] = val

        # B. Expose Bonds
        # Usage: "bonds.A1.balance" or "bonds.A1.factor"
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
                return 0.0 # Graceful degradation or raise error
        
        ctx['bonds'] = BondProxy()

        # C. Expose Variables
        # Usage: "NetWAC"
        for name, val in state.variables.items():
            ctx[name] = val

        # D. Expose Ledgers
        # Usage: "ledgers.CumulativeLoss"
        class LedgerProxy:
            def __getattr__(self, key):
                return state.ledgers.get(key, 0.0)
        ctx['ledgers'] = LedgerProxy()

        return ctx
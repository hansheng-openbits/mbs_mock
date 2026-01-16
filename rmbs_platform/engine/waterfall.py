# In engine/waterfall.py
import logging
from .state import DealState
from .compute import ExpressionEngine

logger = logging.getLogger("RMBS.Waterfall")

class WaterfallRunner:
    def __init__(self, engine: ExpressionEngine):
        self.expr = engine

    def evaluate_period(self, state: DealState):
        """
        Evaluate tests and variables without executing waterfalls.
        Used for historical actuals where cashflows are recorded, not simulated.
        """
        self._run_tests(state)
        self._calculate_variables(state)

    def run_period(self, state: DealState):
        logger.info(f"--- Running Period {state.period_index + 1} ---")

        # STEP 1: Run Tests FIRST (So flags are ready for variables)
        self._run_tests(state)

        # STEP 2: Calculate Variables (Now they can read tests.X.failed)
        self._calculate_variables(state)

        # STEP 3: Run Waterfalls
        logger.info("Executing Interest Waterfall")
        self._execute_waterfall(state, "interest")
        
        logger.info("Executing Principal Waterfall")
        self._execute_waterfall(state, "principal")

        self._allocate_losses(state)

    def _calculate_variables(self, state: DealState):
        # We iterate safely. In a real engine, we would topological sort to handle dependencies.
        for var_name, rule_str in state.def_.variables.items():
            val = self.expr.evaluate(rule_str, state)
            state.set_variable(var_name, val)

    def _run_tests(self, state: DealState):
        """
        Iterates through tests defined in JSON, evaluates them, and sets flags.
        """
        for test in state.def_.tests:
            test_id = test['id']
            
            # A. Calculate Value & Threshold
            val_rule = test['calc'].get('value_rule', '0')
            thresh_rule = test['threshold'].get('rule', '0')
            
            val = self.expr.evaluate(val_rule, state)
            thresh = self.expr.evaluate(thresh_rule, state)
            
            # B. Determine Pass/Fail
            operator = test.get('pass_if', 'VALUE_LT_THRESHOLD')
            passed = False
            
            if operator == 'VALUE_LT_THRESHOLD':
                passed = val < thresh
            elif operator == 'VALUE_LEQ_THRESHOLD':
                passed = val <= thresh
            elif operator == 'VALUE_GT_THRESHOLD':
                passed = val > thresh
            elif operator == 'VALUE_GEQ_THRESHOLD':
                passed = val >= thresh
            
            # C. Set Flags
            # The Compute Proxy looks for state.flags[test_id] to determine .failed
            # If passed=False, then failed=True
            state.flags[test_id] = not passed
            
            # Also handle explicit effects from schema (optional but good practice)
            if not passed:
                for effect in test.get('effects', []):
                    if 'set_flag' in effect:
                        state.flags[effect['set_flag']] = True

            # logger.info(f"Test {test_id}: Val={val}, Thresh={thresh}, Passed={passed}")

    def _execute_waterfall(self, state: DealState, waterfall_type: str):
        wf_def = state.def_.waterfalls.get(waterfall_type, {})
        steps = wf_def.get('steps', [])

        for i, step in enumerate(steps):
            # 1. Condition Check
            condition = step.get('condition', 'true')
            # Now `DelinqTrigger == False` works because variables are populated
            if not self.expr.evaluate_condition(condition, state):
                continue

            # 2. Source Funds
            source_id = step.get('from_fund')
            available = state.cash_balances.get(source_id, 0.0)

            # 3. Target Amount
            amount_rule = step.get('amount_rule', '0')
            target = 0.0
            if amount_rule in ["ALL", "REMAINING"]:
                target = available
            else:
                target = self.expr.evaluate(amount_rule, state)

            # 4. Payment
            payment = min(available, target)
            
            if payment > 0.000001:
                action = step.get('action')
                if action == 'PAY_BOND_INTEREST':
                    self._pay_bond(state, step, payment, is_prin=False)
                elif action == 'PAY_BOND_PRINCIPAL':
                    self._pay_bond(state, step, payment, is_prin=True)
                elif action == 'TRANSFER_FUND':
                    state.transfer_cash(source_id, step.get('to'), payment)
                elif action == 'PAY_FEE':
                    state.withdraw_cash(source_id, payment)

            # 5. Shortfalls
            shortfall = target - payment
            if shortfall > 0.01 and step.get('unpaid_ledger_id'):
                current = state.ledgers.get(step['unpaid_ledger_id'], 0.0)
                state.set_ledger(step['unpaid_ledger_id'], current + shortfall)

    def _pay_bond(self, state: DealState, step: dict, amount: float, is_prin: bool):
        group = step.get('group')
        source = step.get('from_fund')
        if is_prin:
            state.pay_bond_principal(group, amount, source)
        else:
            state.withdraw_cash(source, amount)

    def _allocate_losses(self, state: DealState):
        loss = state.get_variable("RealizedLoss") or 0.0
        if loss <= 0: return
        
        la_def = state.def_.waterfalls.get('loss_allocation', {})
        for bond_id in la_def.get('write_down_order', []):
            if loss <= 0: break
            bond = state.bonds.get(bond_id)
            if bond:
                wd = min(bond.current_balance, loss)
                bond.current_balance -= wd
                loss -= wd
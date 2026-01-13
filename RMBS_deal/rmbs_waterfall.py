import logging
from typing import Dict, Any, List

from rmbs_state import DealState
from rmbs_compute import ExpressionEngine

logger = logging.getLogger("RMBS.Waterfall")

class WaterfallRunner:
    def __init__(self, engine: ExpressionEngine):
        self.expr = engine

    def run_period(self, state: DealState):
        logger.info(f"--- Running Period {state.period_index + 1} ---")
        self._calculate_variables(state)
        self._run_tests(state)

        logger.info("Executing Interest Waterfall")
        self._execute_waterfall(state, "interest")

        logger.info("Executing Principal Waterfall")
        self._execute_waterfall(state, "principal")

        self._allocate_losses(state)

    def _calculate_variables(self, state: DealState):
        for var_name, rule_str in state.def_.variables.items():
            val = self.expr.evaluate(rule_str, state)
            state.set_variable(var_name, val)

    def _run_tests(self, state: DealState):
        pass 

    def _execute_waterfall(self, state: DealState, waterfall_type: str):
        wf_def = state.def_.waterfalls.get(waterfall_type, {})
        steps = wf_def.get('steps', [])

        for i, step in enumerate(steps):
            step_id = step.get('id', str(i))
            
            # A. Check Condition (If false, we genuinely skip)
            condition_rule = step.get('condition', 'true')
            if not self.expr.evaluate_condition(condition_rule, state):
                continue

            # B. Identify Source Funds
            source_id = step.get('from_fund')
            available = state.cash_balances.get(source_id, 0.0)
            
            # --- FIX: REMOVED "SKIP IF EMPTY" CHECK ---
            # We must proceed even if available == 0.0 so we can log shortfalls.

            # C. Calculate Target Amount (How much do we WANT to pay?)
            amount_rule = step.get('amount_rule', '0')
            target_amount = 0.0
            
            if amount_rule == "ALL" or amount_rule == "REMAINING":
                target_amount = available
            else:
                target_amount = self.expr.evaluate(amount_rule, state)

            # D. Determine Actual Payment (Cannot pay what you don't have)
            payment = min(available, target_amount)
            
            # E. Execute Action (Only if we are actually moving money)
            if payment > 0.00001:
                action = step.get('action')
                if action == 'PAY_BOND_INTEREST':
                    self._action_pay_bond(state, step, payment, is_principal=False)
                elif action == 'PAY_BOND_PRINCIPAL':
                    self._action_pay_bond(state, step, payment, is_principal=True)
                elif action == 'TRANSFER_FUND':
                    target_fund = step.get('to')
                    state.transfer_cash(source_id, target_fund, payment)
                    logger.info(f"Step {step_id}: Transferred ${payment:,.2f} {source_id}->{target_fund}")
            
            # F. Handle Shortfalls (Unpaid amounts)
            # This now runs correctly even if payment is 0.0
            shortfall = target_amount - payment
            if shortfall > 0.01:
                self._handle_shortfall(state, step, shortfall)

    def _action_pay_bond(self, state: DealState, step: dict, amount: float, is_principal: bool):
        bond_id = step.get('group')
        source_id = step.get('from_fund')
        
        if is_principal:
            state.pay_bond_principal(bond_id, amount, source_id)
            logger.info(f"Paid Principal ${amount:,.2f} to {bond_id}")
        else:
            state.withdraw_cash(source_id, amount)
            logger.info(f"Paid Interest ${amount:,.2f} to {bond_id}")

    def _handle_shortfall(self, state: DealState, step: dict, amount: float):
        ledger_id = step.get('unpaid_ledger_id')
        if ledger_id:
            current = state.ledgers.get(ledger_id, 0.0)
            state.set_ledger(ledger_id, current + amount)
            logger.warning(f"Shortfall of ${amount:,.2f} on Step {step.get('id')}. Added to {ledger_id}")

    def _allocate_losses(self, state: DealState):
        period_loss = state.get_variable("PeriodRealizedLoss") or 0.0
        if period_loss <= 0: return

        logger.info(f"Allocating Realized Loss: ${period_loss:,.2f}")
        
        la_def = state.def_.waterfalls.get('loss_allocation', {})
        order = la_def.get('write_down_order', [])
        
        remaining_loss = period_loss
        
        for bond_id in order:
            if remaining_loss <= 0: break
            
            bond = state.bonds.get(bond_id)
            if not bond: continue
            
            write_down = min(bond.current_balance, remaining_loss)
            bond.current_balance -= write_down
            remaining_loss -= write_down
            
            logger.warning(f"Wrote down Bond {bond_id} by ${write_down:,.2f}")
            
        cum_loss = state.ledgers.get("CumulativeLoss", 0.0)
        state.set_ledger("CumulativeLoss", cum_loss + period_loss)
"""
Waterfall Execution Engine
==========================

This module provides the waterfall execution logic that allocates collateral
cashflows to bond tranches according to deal rules. The waterfall is the
heart of RMBS deal mechanics, determining how interest and principal are
distributed.

The :class:`WaterfallRunner` executes three phases each period:

1. **Tests**: Evaluate trigger conditions (delinquency, OC tests).
2. **Variables**: Calculate derived values used by waterfall steps.
3. **Waterfalls**: Execute interest, principal, and loss allocation.

A typical RMBS waterfall flows:

1. Interest waterfall: Fees → Senior interest → Subordinate interest
2. Principal waterfall: Senior principal → Subordinate principal
3. Loss allocation: Write down subordinate tranches

Example
-------
>>> from rmbs_platform.engine.waterfall import WaterfallRunner
>>> from rmbs_platform.engine.compute import ExpressionEngine
>>> engine = ExpressionEngine()
>>> runner = WaterfallRunner(engine)
>>> state.deposit_funds("IAF", 50000)
>>> state.deposit_funds("PAF", 100000)
>>> runner.run_period(state)
>>> print(f"Class A balance: ${state.bonds['A'].current_balance:,.0f}")

See Also
--------
compute.ExpressionEngine : Evaluates waterfall conditions and formulas.
state.DealState : Holds the state mutated by the waterfall.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from .compute import ExpressionEngine
from .state import DealState

logger = logging.getLogger("RMBS.Waterfall")


class WaterfallRunner:
    """
    Execute deal tests, variables, and waterfall steps for each period.

    The runner is the main orchestrator of period-by-period deal mechanics.
    It uses the ExpressionEngine to evaluate conditions and formulas,
    and mutates the DealState as cashflows are allocated.

    Parameters
    ----------
    engine : ExpressionEngine
        Expression evaluator for waterfall rules and conditions.

    Attributes
    ----------
    expr : ExpressionEngine
        Reference to the expression engine.

    Example
    -------
    >>> engine = ExpressionEngine()
    >>> runner = WaterfallRunner(engine)
    >>> # Process a period
    >>> runner.run_period(state)
    """

    def __init__(self, engine: ExpressionEngine) -> None:
        """
        Initialize the waterfall runner with an expression engine.

        Parameters
        ----------
        engine : ExpressionEngine
            Engine for evaluating waterfall rules.
        """
        self.expr = engine

    def evaluate_period(self, state: DealState) -> None:
        """
        Evaluate tests and variables for actual periods without paying cashflows.

        This method is used when processing historical (actual) periods where
        we want to evaluate triggers and variables but not execute the
        full waterfall. This preserves tape balances while still computing
        diagnostic values.

        Parameters
        ----------
        state : DealState
            Current deal state to evaluate against.

        Notes
        -----
        This is called when ``apply_waterfall_to_actuals=False`` in the
        simulation configuration. It updates flags and variables but
        does not move cash or pay bonds.

        Example
        -------
        >>> runner.evaluate_period(state)
        >>> triggered = state.flags.get("DelinqTest", False)
        """
        self._run_tests(state)
        self._calculate_variables(state)

    def run_period(self, state: DealState) -> None:
        """
        Run a full period including tests, variables, waterfalls, and losses.

        This is the main entry point for period processing. It executes
        the complete deal mechanics:

        1. Run tests to set trigger flags.
        2. Calculate variables for waterfall conditions.
        3. Execute interest waterfall.
        4. Execute principal waterfall.
        5. Allocate losses to subordinate tranches.

        Parameters
        ----------
        state : DealState
            Current deal state to mutate.

        Notes
        -----
        The method logs the period number for debugging. After execution,
        the state's cash_balances should be mostly depleted (swept to
        bonds or retained per deal rules).

        Example
        -------
        >>> state.deposit_funds("IAF", 50000)
        >>> state.deposit_funds("PAF", 100000)
        >>> runner.run_period(state)
        >>> # Cash has been paid to bonds
        >>> print(f"Remaining IAF: ${state.cash_balances['IAF']:,.2f}")
        """
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

        # STEP 4: Allocate Losses
        self._allocate_losses(state)

    def _calculate_variables(self, state: DealState) -> None:
        """
        Compute derived variables used by waterfall steps and tests.

        Variables are defined in the deal specification as expression
        strings. This method evaluates each variable and stores the
        result in state.variables for use by subsequent waterfall steps.

        Parameters
        ----------
        state : DealState
            Current deal state.

        Notes
        -----
        Variables are evaluated in definition order. For deals with
        variable dependencies, the deal spec should order variables
        such that dependencies are calculated first.

        Example
        -------
        >>> # Variables like "OC_Ratio" = "collateral.current_balance / bonds.A.balance"
        >>> runner._calculate_variables(state)
        >>> print(f"OC Ratio: {state.get_variable('OC_Ratio'):.2%}")
        """
        for var_name, rule_str in state.def_.variables.items():
            val = self.expr.evaluate(rule_str, state)
            state.set_variable(var_name, val)

    def _run_tests(self, state: DealState) -> None:
        """
        Evaluate deal tests (e.g., triggers) and set pass/fail flags.

        Tests are defined in the deal specification with:
        - A calculation rule for the test value
        - A threshold rule for the comparison
        - A pass condition (VALUE_LT_THRESHOLD, etc.)

        The test result is stored in state.flags[test_id] where:
        - True = test FAILED (trigger condition met)
        - False = test PASSED

        Parameters
        ----------
        state : DealState
            Current deal state.

        Notes
        -----
        **Test Types**:
        - ``VALUE_LT_THRESHOLD``: Pass if value < threshold
        - ``VALUE_LEQ_THRESHOLD``: Pass if value <= threshold
        - ``VALUE_GT_THRESHOLD``: Pass if value > threshold
        - ``VALUE_GEQ_THRESHOLD``: Pass if value >= threshold

        **Effects**: Tests can define effects that set additional flags
        when the test fails, enabling trigger cascades.

        Example
        -------
        >>> # Delinquency test: Pass if delinq < 10%
        >>> runner._run_tests(state)
        >>> if state.flags.get("DelinqTest"):
        ...     print("Delinquency trigger breached!")
        """
        for test in state.def_.tests:
            test_id = test["id"]

            # A. Calculate Value & Threshold
            val_rule = test["calc"].get("value_rule", "0")
            thresh_rule = test["threshold"].get("rule", "0")

            val = self.expr.evaluate(val_rule, state)
            thresh = self.expr.evaluate(thresh_rule, state)

            # B. Determine Pass/Fail
            operator = test.get("pass_if", "VALUE_LT_THRESHOLD")
            passed = False

            if operator == "VALUE_LT_THRESHOLD":
                passed = val < thresh
            elif operator == "VALUE_LEQ_THRESHOLD":
                passed = val <= thresh
            elif operator == "VALUE_GT_THRESHOLD":
                passed = val > thresh
            elif operator == "VALUE_GEQ_THRESHOLD":
                passed = val >= thresh

            # C. Set Flags (failed = not passed)
            state.flags[test_id] = not passed

            # Handle explicit effects from schema
            if not passed:
                for effect in test.get("effects", []):
                    if "set_flag" in effect:
                        state.flags[effect["set_flag"]] = True

    def _execute_waterfall(self, state: DealState, waterfall_type: str) -> None:
        """
        Execute one waterfall (interest or principal) for the period.

        The waterfall processes steps sequentially, checking conditions
        and making payments from source funds to targets (bonds, fees,
        or other funds).

        Parameters
        ----------
        state : DealState
            Current deal state.
        waterfall_type : str
            Which waterfall to execute: "interest" or "principal".

        Notes
        -----
        **Step Processing**:

        1. Check condition (skip if False).
        2. Determine available funds in source bucket.
        3. Calculate target payment amount.
        4. Pay the minimum of available and target.
        5. Record any shortfall in the specified ledger.

        **Actions**:
        - ``PAY_BOND_INTEREST``: Pay interest to a bond group.
        - ``PAY_BOND_PRINCIPAL``: Pay principal to a bond group.
        - ``TRANSFER_FUND``: Move cash between funds.
        - ``PAY_FEE``: Pay a fee (cash leaves the structure).

        Example
        -------
        >>> runner._execute_waterfall(state, "interest")
        >>> # Interest has been paid to bonds based on priority
        """
        wf_def = state.def_.waterfalls.get(waterfall_type, {})
        steps = wf_def.get("steps", [])

        for i, step in enumerate(steps):
            # 1. Condition Check
            condition = step.get("condition", "true")
            if not self.expr.evaluate_condition(condition, state):
                continue

            # 2. Source Funds
            source_id = step.get("from_fund")
            available = state.cash_balances.get(source_id, 0.0)

            # 3. Target Amount
            amount_rule = step.get("amount_rule", "0")
            target = 0.0
            if amount_rule in ["ALL", "REMAINING"]:
                target = available
            else:
                target = self.expr.evaluate(amount_rule, state)

            # 4. Payment (capped at available)
            payment = min(available, target)

            if payment > 0.000001:
                action = step.get("action")
                if action == "PAY_BOND_INTEREST":
                    self._pay_bond(state, step, payment, is_prin=False)
                elif action == "PAY_BOND_PRINCIPAL":
                    self._pay_bond(state, step, payment, is_prin=True)
                elif action == "TRANSFER_FUND":
                    state.transfer_cash(source_id, step.get("to"), payment)
                elif action == "PAY_FEE":
                    state.withdraw_cash(source_id, payment)

            # 5. Shortfalls
            shortfall = target - payment
            if shortfall > 0.01 and step.get("unpaid_ledger_id"):
                current = state.ledgers.get(step["unpaid_ledger_id"], 0.0)
                state.set_ledger(step["unpaid_ledger_id"], current + shortfall)

    def _pay_bond(
        self, state: DealState, step: Dict[str, Any], amount: float, is_prin: bool
    ) -> None:
        """
        Route a payment to interest or principal for a bond group.

        Parameters
        ----------
        state : DealState
            Current deal state.
        step : dict
            Waterfall step definition containing group and source.
        amount : float
            Payment amount.
        is_prin : bool
            True for principal payment, False for interest.

        Notes
        -----
        For interest payments, cash is simply withdrawn from the source
        fund (simplified model without detailed interest tracking).
        For principal payments, the bond balance is reduced.
        """
        group = step.get("group")
        source = step.get("from_fund")
        if is_prin:
            state.pay_bond_principal(group, amount, source)
        else:
            # Interest payment - just withdraw cash
            state.withdraw_cash(source, amount)

    def _allocate_losses(self, state: DealState) -> None:
        """
        Allocate realized losses to bonds based on loss allocation rules.

        Losses are typically allocated in reverse seniority order,
        writing down subordinate tranches first before touching
        senior tranches.

        Parameters
        ----------
        state : DealState
            Current deal state with RealizedLoss variable set.

        Notes
        -----
        The write-down order is defined in
        ``state.def_.waterfalls.loss_allocation.write_down_order``.

        Losses are allocated until either:
        - All losses are absorbed.
        - All subordinate tranches are written to zero.

        Example
        -------
        >>> state.set_variable("RealizedLoss", 50000)
        >>> runner._allocate_losses(state)
        >>> # Subordinate tranches have been written down
        """
        loss = state.get_variable("RealizedLoss") or 0.0
        if loss <= 0:
            return

        la_def = state.def_.waterfalls.get("loss_allocation", {})
        for bond_id in la_def.get("write_down_order", []):
            if loss <= 0:
                break
            bond = state.bonds.get(bond_id)
            if bond:
                wd = min(bond.current_balance, loss)
                bond.current_balance -= wd
                loss -= wd

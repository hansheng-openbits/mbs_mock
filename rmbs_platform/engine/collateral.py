import pandas as pd
import numpy as np
from dataclasses import dataclass

@dataclass
class PeriodCashflow:
    period: int
    scheduled_interest: float
    scheduled_principal: float
    prepayments: float
    defaults: float
    recoveries: float
    total_interest_collected: float
    total_principal_collected: float

class CollateralModel:
    def __init__(self, original_balance: float, wac: float, wam: int):
        self.original_balance = original_balance
        self.wac = wac
        self.wam = wam
        self.current_balance = original_balance
        self.current_period = 0

    def generate_cashflows(self, periods: int, cpr_vector: float, cdr_vector: float, sev_vector: float, start_balance: float = None) -> pd.DataFrame:
        """
        Generates a DataFrame of asset cashflows for N periods based on assumptions.
        CPR: Constant Prepayment Rate (Annualized)
        CDR: Constant Default Rate (Annualized)
        SEV: Severity (Loss Given Default)
        """
        rows = []
        balance = self.original_balance if start_balance is None else start_balance
        
        # Monthly Rates
        r_gwac = self.wac / 12.0
        
        for t in range(1, periods + 1):
            if balance <= 0:
                rows.append([t, 0, 0, 0, 0, 0, 0, 0, 0])
                continue

            # 1. Calculate Rates (SMM = Single Monthly Mortality)
            smm_prepay = 1 - (1 - cpr_vector)**(1/12)
            mdr_default = 1 - (1 - cdr_vector)**(1/12)
            
            # 2. Interest Due
            interest_due = balance * r_gwac
            
            # 3. Principal Waterfall on Assets
            # Scheduled Amortization (simplified Mortgage formula)
            remaining_term = max(1, self.wam - t)
            level_pay = (balance * r_gwac) / (1 - (1 + r_gwac)**(-remaining_term))
            sched_prin = max(0, level_pay - interest_due)
            
            # Defaults (occur on Start Balance)
            default_amount = balance * mdr_default
            loss_amount = default_amount * sev_vector
            recovery_amount = default_amount - loss_amount
            
            # Prepayments (occur on Balance post-Scheduled)
            bal_post_sched = balance - sched_prin - default_amount
            prepay_amount = max(0, bal_post_sched * smm_prepay)
            
            # 4. Aggregates
            total_prin_collected = sched_prin + prepay_amount + recovery_amount
            total_int_collected = interest_due  # Simplified (ignoring servicer advances logic for now)
            
            # 5. Update Balance
            balance = balance - sched_prin - default_amount - prepay_amount
            
            rows.append({
                "Period": t,
                "BeginBalance": balance + sched_prin + default_amount + prepay_amount,
                "EndBalance": balance,
                "InterestCollected": total_int_collected,
                "PrincipalCollected": total_prin_collected, # Note: Recoveries usually go to Prin in RMBS
                "RealizedLoss": loss_amount,
                "DefaultAmount": default_amount
            })
            
        return pd.DataFrame(rows)
"""
ML Configuration
================

Shared configuration constants for the Freddie Mac ML pipeline, including
historical market rate data and performance tape column definitions.

Constants
---------
TIME_COLS : list of str
    Column names for Freddie Mac monthly performance tape.
MARKET_RATES : dict
    Historical 30-year mortgage rates by YYYYMM period.
    Used for rate incentive calculations.

Example
-------
>>> from rmbs_platform.ml.config import MARKET_RATES
>>> rate_201901 = MARKET_RATES.get(201901, 4.0)
>>> print(f"Jan 2019 rate: {rate_201901:.2f}%")

Notes
-----
Market rates are sourced from Freddie Mac's Primary Mortgage Market Survey
(PMMS). These rates are used to calculate rate incentive features for
prepayment modeling.
"""

from __future__ import annotations

from typing import Dict, List

# Freddie Mac performance tape column names
# These are the standard column names in Freddie Mac's monthly performance files
TIME_COLS: List[str] = [
    "LOAN_SEQUENCE_NUMBER",
    "MONTHLY_REPORTING_PERIOD",
    "CURRENT_ACTUAL_UPB",
    "CURRENT_LOAN_DELINQUENCY_STATUS",
    "LOAN_AGE",
    "REMAINING_MONTHS_TO_LEGAL_MATURITY",
    "REPURCHASE_FLAG",
    "MODIFICATION_FLAG",
    "ZERO_BALANCE_CODE",
    "ZERO_BALANCE_EFFECTIVE_DATE",
    "CURRENT_INTEREST_RATE",
    "CURRENT_DEFERRED_UPB",
    "DUE_DATE_OF_LAST_PAID_INSTALLMENT",
    "MI_RECOVERIES",
    "NET_SALES_PROCEEDS",
    "NON_MI_RECOVERIES",
    "EXPENSES",
    "LEGAL_COSTS",
    "MAINTENANCE_AND_PRESERVATION_COSTS",
    "TAXES_AND_INSURANCE",
    "MISC_EXPENSES",
    "ACTUAL_LOSS_CALCULATION",
    "MODIFICATION_COST",
    "STEP_MODIFICATION_FLAG",
    "DEFERRED_PAYMENT_PLAN",
    "ESTIMATED_LOAN_TO_VALUE",
    "ZERO_BALANCE_REMOVAL_UPB",
    "DELINQUENT_ACCRUED_INTEREST",
    "DELINQUENCY_DUE_TO_DISASTER",
    "BORROWER_ASSISTANCE_STATUS_CODE",
    "CURRENT_MONTH_MODIFICATION_COST",
    "INTEREST_BEARING_UPB",
    "SOURCE_QUARTER",
]

# Historical 30-year fixed mortgage rates by month (YYYYMM: rate%)
# Source: Freddie Mac Primary Mortgage Market Survey
MARKET_RATES: Dict[int, float] = {
    # 2017
    201701: 4.15,
    201702: 4.17,
    201703: 4.20,
    201704: 4.05,
    201705: 4.01,
    201706: 3.90,
    201707: 3.97,
    201708: 3.88,
    201709: 3.81,
    201710: 3.90,
    201711: 3.92,
    201712: 3.95,
    # 2018
    201801: 4.03,
    201802: 4.33,
    201803: 4.44,
    201804: 4.47,
    201805: 4.59,
    201806: 4.57,
    201807: 4.53,
    201808: 4.55,
    201809: 4.63,
    201810: 4.83,
    201811: 4.87,
    201812: 4.64,
    # 2019
    201901: 4.46,
    201902: 4.37,
    201903: 4.27,
    201904: 4.14,
    201905: 4.07,
    201906: 3.80,
    201907: 3.77,
    201908: 3.62,
    201909: 3.61,
    201910: 3.69,
    201911: 3.70,
    201912: 3.72,
    # 2020
    202001: 3.62,
    202002: 3.47,
    202003: 3.45,
    202004: 3.31,
    202005: 3.23,
    202006: 3.16,
    202007: 3.02,
    202008: 2.94,
    202009: 2.89,
    202010: 2.83,
    202011: 2.77,
    202012: 2.68,
    # 2021
    202101: 2.74,
    202102: 2.81,
    202103: 3.08,
    202104: 3.06,
    202105: 2.96,
    202106: 2.98,
    202107: 2.87,
    202108: 2.84,
    202109: 2.90,
    202110: 3.07,
    202111: 3.07,
    202112: 3.10,
    # 2022
    202201: 3.45,
    202202: 3.76,
    202203: 4.17,
    202204: 4.98,
    202205: 5.23,
    202206: 5.52,
    202207: 5.41,
    202208: 5.22,
    202209: 6.11,
    202210: 6.90,
    202211: 6.76,
    202212: 6.35,
    # 2023
    202301: 6.25,
    202302: 6.30,
    202303: 6.54,
    202304: 6.34,
    202305: 6.43,
    202306: 6.71,
    202307: 6.84,
    202308: 7.07,
    202309: 7.20,
    202310: 7.62,
    202311: 7.44,
    202312: 6.82,
    # 2024
    202401: 6.64,
    202402: 6.78,
    202403: 6.82,
    202404: 6.99,
    202405: 7.06,
    202406: 6.92,
    202407: 6.82,
    202408: 6.50,
    202409: 6.18,
    202410: 6.43,
    202411: 6.81,
    202412: 6.72,
}

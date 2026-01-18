import tempfile
from pathlib import Path
import unittest

import pandas as pd

from rmbs_platform.ml.config import TIME_COLS
from rmbs_platform.ml.etl_freddie import build_survival_dataset


class TestFreddieEtl(unittest.TestCase):
    def test_build_survival_dataset(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            orig_file = tmpdir_path / "orig.csv"
            perf_file = tmpdir_path / "perf.csv"
            output_file = tmpdir_path / "out.csv"

            orig = pd.DataFrame(
                [
                    {
                        "LOAN_SEQUENCE_NUMBER": "L1",
                        "FIRST_PAYMENT_DATE": 201701,
                        "ORIGINAL_INTEREST_RATE": 4.5,
                        "CREDIT_SCORE": 720,
                        "ORIGINAL_LTV": 75,
                        "ORIGINAL_DEBT_TO_INCOME_RATIO": 35,
                    },
                    {
                        "LOAN_SEQUENCE_NUMBER": "L2",
                        "FIRST_PAYMENT_DATE": 201702,
                        "ORIGINAL_INTEREST_RATE": 5.0,
                        "CREDIT_SCORE": 680,
                        "ORIGINAL_LTV": 85,
                        "ORIGINAL_DEBT_TO_INCOME_RATIO": 45,
                    },
                ]
            )
            orig.to_csv(orig_file, sep="|", index=False)

            perf = pd.DataFrame(
                [
                    {
                        "LOAN_SEQUENCE_NUMBER": "L1",
                        "LOAN_AGE": 10,
                        "ZERO_BALANCE_CODE": 1,
                        "CURRENT_LOAN_DELINQUENCY_STATUS": 0,
                    },
                    {
                        "LOAN_SEQUENCE_NUMBER": "L2",
                        "LOAN_AGE": 12,
                        "ZERO_BALANCE_CODE": 3,
                        "CURRENT_LOAN_DELINQUENCY_STATUS": 0,
                    },
                ]
            )
            for col in TIME_COLS:
                if col not in perf.columns:
                    perf[col] = None
            perf = perf[TIME_COLS]
            perf.to_csv(perf_file, sep="|", index=False)

            result = build_survival_dataset(str(orig_file), str(perf_file), str(output_file))
            self.assertTrue(output_file.exists())
            self.assertEqual(len(result), 2)

            events = dict(zip(result["LOAN_SEQUENCE_NUMBER"], result["EVENT"]))
            durations = dict(zip(result["LOAN_SEQUENCE_NUMBER"], result["DURATION"]))
            self.assertEqual(events["L1"], 1)
            self.assertEqual(durations["L1"], 10)
            self.assertEqual(events["L2"], 2)
            self.assertEqual(durations["L2"], 12)


if __name__ == "__main__":
    unittest.main()

"""
ML Module for Prepayment and Default Modeling
=============================================

This package provides machine learning utilities for projecting mortgage
prepayment and default behavior in RMBS cashflow simulations.

Submodules
----------
config
    Shared configuration including market rate data and column definitions.
models
    ML model wrappers (CoxPH, RandomSurvivalForest) and rate generators.
features
    Feature engineering for prepay/default modeling (rate incentive, SATO).
portfolio
    Portfolio-level simulation using trained ML models.
etl_freddie
    ETL utilities for Freddie Mac origination/performance tapes.
train_prepay
    Training scripts for prepayment models.
train_default
    Training scripts for default models.

Example
-------
>>> from rmbs_platform.ml.models import UniversalModel, StochasticRateModel
>>> from rmbs_platform.ml.portfolio import DataManager, SurveillanceEngine
>>> # Load loan data
>>> data_mgr = DataManager("origination.csv")
>>> pool = data_mgr.get_pool()
>>> # Generate rate scenarios
>>> vasicek = StochasticRateModel()
>>> rates = vasicek.generate_paths(60, start_rate=0.045, shock_scenario="rally")
>>> # Run ML simulation
>>> prepay_model = UniversalModel("models/prepay.pkl", "Prepay")
>>> default_model = UniversalModel("models/default.pkl", "Default")
>>> engine = SurveillanceEngine(pool, prepay_model, default_model)
>>> cashflows = engine.run(rates)

See Also
--------
engine : Core simulation engine that integrates ML models.
"""

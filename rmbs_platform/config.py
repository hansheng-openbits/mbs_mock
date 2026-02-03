"""
RMBS Platform Configuration
===========================

Centralized configuration management using environment variables with sensible
defaults. Follows the 12-factor app methodology for cloud-native deployments.

This module provides a singleton ``Settings`` instance that loads configuration
from environment variables prefixed with ``RMBS_``. All settings have defaults
suitable for local development.

Environment Variables
---------------------
RMBS_API_HOST : str
    Host address for the API server (default: "127.0.0.1").
RMBS_API_PORT : int
    Port for the API server (default: 8000).
RMBS_LOG_LEVEL : str
    Logging level (DEBUG, INFO, WARNING, ERROR).

Example
-------
Using environment variables::

    export RMBS_API_PORT=9000
    export RMBS_LOG_LEVEL=DEBUG
    python -m uvicorn rmbs_platform.api_main:app

Accessing settings in code::

    from rmbs_platform.config import settings
    print(f"API running on port {settings.api_port}")
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

# Determine the package root directory
_PACKAGE_ROOT = Path(__file__).resolve().parent


def _get_env(key: str, default: Any, value_type: type = str) -> Any:
    """
    Get an environment variable with type conversion.

    Parameters
    ----------
    key : str
        Environment variable name (will be prefixed with RMBS_).
    default : Any
        Default value if not set.
    value_type : type
        Type to convert to (str, int, float, bool, list).

    Returns
    -------
    Any
        The environment variable value converted to the specified type.
    """
    env_name = f"RMBS_{key.upper()}"
    env_value = os.environ.get(env_name)

    if env_value is None:
        return default

    try:
        if value_type == bool:
            return env_value.lower() in ("true", "1", "yes", "on")
        elif value_type == int:
            return int(env_value)
        elif value_type == float:
            return float(env_value)
        elif value_type == list:
            try:
                return json.loads(env_value)
            except json.JSONDecodeError:
                return env_value.split(",")
        else:
            return env_value
    except (ValueError, TypeError):
        return default


class Settings:
    """
    Application configuration loaded from environment variables.

    All settings have sensible defaults for local development. In production,
    override via environment variables prefixed with ``RMBS_``.

    Example
    -------
    >>> from rmbs_platform.config import settings
    >>> print(f"Deals stored in: {settings.deals_dir}")
    """

    def __init__(self) -> None:
        """Initialize settings from environment variables."""
        # =====================================================================
        # API Server Configuration
        # =====================================================================
        self.api_host: str = _get_env("API_HOST", "127.0.0.1", str)
        self.api_port: int = _get_env("API_PORT", 8000, int)
        self.api_workers: int = _get_env("API_WORKERS", 1, int)
        self.api_reload: bool = _get_env("API_RELOAD", False, bool)

        # =====================================================================
        # Storage Paths
        # =====================================================================
        self.deals_dir: str = _get_env("DEALS_DIR", str(_PACKAGE_ROOT / "deals"), str)
        self.collateral_dir: str = _get_env("COLLATERAL_DIR", str(_PACKAGE_ROOT / "collateral"), str)
        self.performance_dir: str = _get_env("PERFORMANCE_DIR", str(_PACKAGE_ROOT / "performance"), str)
        self.models_dir: str = _get_env("MODELS_DIR", str(_PACKAGE_ROOT / "models"), str)
        self.scenarios_dir: str = _get_env("SCENARIOS_DIR", str(_PACKAGE_ROOT / "scenarios"), str)
        self.results_dir: str = _get_env("RESULTS_DIR", str(_PACKAGE_ROOT / "results"), str)
        self.audit_log_path: str = _get_env("AUDIT_LOG_PATH", str(_PACKAGE_ROOT / "results" / "audit_events.jsonl"), str)

        # Versioned storage directories
        self.deals_versions_dir: str = _get_env("DEALS_VERSIONS_DIR", str(_PACKAGE_ROOT / "deals_versions"), str)
        self.collateral_versions_dir: str = _get_env("COLLATERAL_VERSIONS_DIR", str(_PACKAGE_ROOT / "collateral_versions"), str)
        self.performance_versions_dir: str = _get_env("PERFORMANCE_VERSIONS_DIR", str(_PACKAGE_ROOT / "performance_versions"), str)
        self.scenarios_versions_dir: str = _get_env("SCENARIOS_VERSIONS_DIR", str(_PACKAGE_ROOT / "scenarios_versions"), str)

        # =====================================================================
        # Logging Configuration
        # =====================================================================
        self.log_level: str = _get_env("LOG_LEVEL", "INFO", str)
        self.log_format: str = _get_env("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - %(message)s", str)

        # =====================================================================
        # Security & CORS
        # =====================================================================
        self.enable_cors: bool = _get_env("ENABLE_CORS", True, bool)
        self.cors_origins: List[str] = _get_env("CORS_ORIGINS", ["http://localhost:8501", "http://127.0.0.1:8501"], list)
        self.require_rbac: bool = _get_env("REQUIRE_RBAC", True, bool)

        # =====================================================================
        # Upload & Performance Limits
        # =====================================================================
        self.max_upload_size_mb: int = _get_env("MAX_UPLOAD_SIZE_MB", 100, int)
        self.job_timeout_seconds: int = _get_env("JOB_TIMEOUT_SECONDS", 600, int)
        self.max_concurrent_jobs: int = _get_env("MAX_CONCURRENT_JOBS", 10, int)

        # =====================================================================
        # Simulation Defaults
        # =====================================================================
        self.default_horizon_periods: int = _get_env("DEFAULT_HORIZON_PERIODS", 60, int)
        self.default_cpr: float = _get_env("DEFAULT_CPR", 0.10, float)
        self.default_cdr: float = _get_env("DEFAULT_CDR", 0.01, float)
        self.default_severity: float = _get_env("DEFAULT_SEVERITY", 0.40, float)
        self.default_recovery_lag_months: int = _get_env("DEFAULT_RECOVERY_LAG_MONTHS", 12, int)

        # =====================================================================
        # ML Model Configuration
        # =====================================================================
        self.ml_enabled_by_default: bool = _get_env("ML_ENABLED_BY_DEFAULT", False, bool)
        self.default_rate_scenario: str = _get_env("DEFAULT_RATE_SCENARIO", "base", str)
        self.default_start_rate: float = _get_env("DEFAULT_START_RATE", 0.045, float)
        self.default_rate_sensitivity: float = _get_env("DEFAULT_RATE_SENSITIVITY", 1.0, float)
        self.default_feature_source: str = _get_env("DEFAULT_FEATURE_SOURCE", "simulated", str)

        # =====================================================================
        # Loss Severity Model Parameters
        # =====================================================================
        self.severity_model_enabled: bool = _get_env("SEVERITY_MODEL_ENABLED", True, bool)
        self.severity_base: float = _get_env("SEVERITY_BASE", 0.35, float)
        self.severity_ltv_coefficient: float = _get_env("SEVERITY_LTV_COEFFICIENT", 0.004, float)
        self.severity_fico_coefficient: float = _get_env("SEVERITY_FICO_COEFFICIENT", -0.0002, float)
        self.severity_hpi_sensitivity: float = _get_env("SEVERITY_HPI_SENSITIVITY", 0.15, float)
        self.severity_min: float = _get_env("SEVERITY_MIN", 0.10, float)
        self.severity_max: float = _get_env("SEVERITY_MAX", 0.80, float)

        # =====================================================================
        # Clean-Up Call Configuration
        # =====================================================================
        self.cleanup_call_enabled: bool = _get_env("CLEANUP_CALL_ENABLED", True, bool)
        self.cleanup_call_threshold: float = _get_env("CLEANUP_CALL_THRESHOLD", 0.10, float)

        # =====================================================================
        # Database & Cache (Future Use)
        # =====================================================================
        self.database_url: Optional[str] = _get_env("DATABASE_URL", None, str)
        self.redis_url: Optional[str] = _get_env("REDIS_URL", None, str)

        # =====================================================================
        # Web3 Integration
        # =====================================================================
        self.web3_enabled: bool = _get_env("WEB3_ENABLED", False, bool)
        self.web3_rpc_url: str = _get_env("WEB3_RPC_URL", "", str)
        self.web3_admin_private_key: str = _get_env("WEB3_ADMIN_PRIVATE_KEY", "", str)
        self.web3_default_gas: int = _get_env("WEB3_DEFAULT_GAS", 1_000_000, int)
        self.web3_tranche_factory: str = _get_env("WEB3_TRANCHE_FACTORY", "", str)
        self.web3_transfer_validator: str = _get_env("WEB3_TRANSFER_VALIDATOR", "", str)
        self.web3_servicer_oracle: str = _get_env("WEB3_SERVICER_ORACLE", "", str)
        self.web3_waterfall_engine: str = _get_env("WEB3_WATERFALL_ENGINE", "", str)
        self.web3_loan_nft: str = _get_env("WEB3_LOAN_NFT", "", str)

    @property
    def package_root(self) -> Path:
        """Return the package root directory."""
        return _PACKAGE_ROOT

    @property
    def log_level_int(self) -> int:
        """Return the log level as an integer constant."""
        return getattr(logging, self.log_level.upper(), logging.INFO)

    @property
    def max_upload_bytes(self) -> int:
        """Return maximum upload size in bytes."""
        return self.max_upload_size_mb * 1024 * 1024

    def get_path(self, name: str) -> Path:
        """
        Get a storage path as a Path object, creating it if necessary.

        Parameters
        ----------
        name : str
            Name of the path setting (deals_dir, models_dir, etc.).

        Returns
        -------
        Path
            Resolved Path object.
        """
        path_str = getattr(self, name, None)
        if path_str is None:
            raise ValueError(f"Unknown path setting: {name}")
        path = Path(path_str)
        if not path.is_absolute():
            path = _PACKAGE_ROOT / path
        path.mkdir(parents=True, exist_ok=True)
        return path.resolve()

    def configure_logging(self) -> None:
        """
        Configure application logging based on settings.

        Sets up the root logger with the configured level and format.
        """
        logging.basicConfig(
            level=self.log_level_int,
            format=self.log_format,
        )
        # Quiet noisy loggers
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


@lru_cache()
def get_settings() -> Settings:
    """
    Return the cached application settings instance.

    This function uses LRU caching to ensure settings are loaded only once
    and reused throughout the application lifetime.

    Returns
    -------
    Settings
        Application settings instance.

    Example
    -------
    >>> settings = get_settings()
    >>> print(settings.api_port)
    8000
    """
    return Settings()


# Module-level singleton for convenience
settings = get_settings()


# ============================================================================
# Validation Functions
# ============================================================================


def validate_storage_paths() -> None:
    """
    Validate and create all required storage directories.

    Raises
    ------
    PermissionError
        If directories cannot be created due to permissions.
    """
    path_attrs = [
        "deals_dir",
        "collateral_dir",
        "performance_dir",
        "models_dir",
        "scenarios_dir",
        "results_dir",
        "deals_versions_dir",
        "collateral_versions_dir",
        "performance_versions_dir",
        "scenarios_versions_dir",
    ]
    for attr in path_attrs:
        settings.get_path(attr)

    # Ensure audit log parent directory exists
    audit_path = Path(settings.audit_log_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)


def get_model_registry_path() -> Path:
    """
    Return the path to the ML model registry file.

    Returns
    -------
    Path
        Path to model_registry.json.
    """
    return Path(settings.models_dir) / "model_registry.json"


def get_severity_parameters() -> Dict[str, Any]:
    """
    Return loss severity model parameters as a dictionary.

    Returns
    -------
    dict
        Severity model configuration.

    Example
    -------
    >>> params = get_severity_parameters()
    >>> print(f"Base severity: {params['base']:.0%}")
    """
    return {
        "enabled": settings.severity_model_enabled,
        "base": settings.severity_base,
        "ltv_coefficient": settings.severity_ltv_coefficient,
        "fico_coefficient": settings.severity_fico_coefficient,
        "hpi_sensitivity": settings.severity_hpi_sensitivity,
        "min": settings.severity_min,
        "max": settings.severity_max,
    }

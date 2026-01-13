import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Any, List, Optional, Set

# dependency: pip install jsonschema
from jsonschema import validate, ValidationError

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RMBS.Loader")

# --- CUSTOM EXCEPTIONS ---
class DealLoadError(Exception):
    """Base exception for deal loading issues."""
    pass

class SchemaViolationError(DealLoadError):
    """Raised when the JSON structure is invalid."""
    pass

class LogicIntegrityError(DealLoadError):
    """Raised when logic references (IDs) are broken."""
    pass

# --- ENUMS (Type Safety) ---
class DayCount(str, Enum):
    DC_30_360 = "30_360"
    ACT_360 = "ACT_360"
    ACT_365 = "ACT_365"
    ACT_ACT = "ACT_ACT"

class CouponType(str, Enum):
    FIXED = "FIXED"
    FLOAT = "FLOAT"
    WAC = "WAC"
    VARIABLE = "VARIABLE"

# --- IMMUTABLE DOMAIN OBJECTS ---
@dataclass(frozen=True)
class Bond:
    id: str
    type: str
    original_balance: float
    coupon_type: CouponType
    priority_interest: int
    priority_principal: int
    interest_rules: Dict[str, Any] = field(default_factory=dict)
    
    # Optional fields for Coupon details
    fixed_rate: Optional[float] = None
    variable_cap_ref: Optional[str] = None

@dataclass(frozen=True)
class Fund:
    id: str
    description: str

@dataclass(frozen=True)
class Account:
    id: str
    type: str

@dataclass(frozen=True)
class DealDefinition:
    """
    The immutable, validated definition of the deal.
    """
    meta: Dict[str, Any]
    dates: Dict[str, Any]
    bonds: Dict[str, Bond]
    accounts: Dict[str, Account]
    funds: Dict[str, Fund]
    variables: Dict[str, str] # ID -> Expression
    waterfalls: Dict[str, Any]
    
    def get_bond(self, bond_id: str) -> Bond:
        return self.bonds.get(bond_id)

# --- THE LOADER MODULE ---

class DealLoader:
    def __init__(self, schema_path: str = None):
        """
        Initialize with a path to the JSON Schema file.
        """
        self.schema = self._load_schema(schema_path) if schema_path else None

    def _load_schema(self, path: str) -> dict:
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load schema file: {path}")
            raise e

    def load_from_json(self, json_data: Dict[str, Any]) -> DealDefinition:
        logger.info(f"Loading deal: {json_data.get('meta', {}).get('deal_id', 'Unknown')}")

        # 1. Syntactic Validation
        self._validate_syntax(json_data)

        # 2. Hydration (Data Transformation)
        deal = self._hydrate_objects(json_data)

        # 3. Semantic Validation (Business Logic Integrity)
        self._validate_semantics(deal, json_data)

        logger.info("Deal loaded and validated successfully.")
        return deal

    def _validate_syntax(self, data: Dict[str, Any]):
        if not self.schema:
            logger.warning("No JSON Schema provided. Skipping syntactic validation.")
            return
        
        try:
            validate(instance=data, schema=self.schema)
        except ValidationError as e:
            logger.error(f"Schema Validation Failed at {e.path}: {e.message}")
            raise SchemaViolationError(f"Invalid JSON Structure: {e.message}")

    def _hydrate_objects(self, data: Dict[str, Any]) -> DealDefinition:
        try:
            # Hydrate Funds
            funds = {
                f['id']: Fund(id=f['id'], description=f.get('description', ''))
                for f in data.get('funds', [])
            }

            # Hydrate Accounts
            accounts = {
                a['id']: Account(id=a['id'], type=a['type'])
                for a in data.get('accounts', [])
            }

            # Hydrate Bonds (with Enum conversion)
            bonds = {}
            for b in data.get('bonds', []):
                # Safe Enum Conversion
                try:
                    c_kind = CouponType(b['coupon']['kind'])
                except ValueError:
                    raise SchemaViolationError(f"Unknown coupon kind: {b['coupon']['kind']}")

                bond = Bond(
                    id=b['id'],
                    type=b['type'],
                    original_balance=b['original_balance'],
                    coupon_type=c_kind,
                    priority_interest=b['priority']['interest'],
                    priority_principal=b['priority']['principal'],
                    interest_rules=b.get('interest_rules', {}),
                    fixed_rate=b['coupon'].get('fixed_rate'),
                    variable_cap_ref=b['coupon'].get('variable_cap')
                )
                bonds[b['id']] = bond

            # Hydrate Variables (Dictionary of Expressions)
            variables = data.get('variables', {})

            return DealDefinition(
                meta=data['meta'],
                dates=data['dates'],
                bonds=bonds,
                accounts=accounts,
                funds=funds,
                variables=variables,
                waterfalls=data['waterfalls']
            )

        except KeyError as e:
            # Defensive programming: Should be caught by schema validation, 
            # but this catches issues if schema validation is skipped.
            logger.error(f"Missing required field during hydration: {e}")
            raise SchemaViolationError(f"Missing required field: {e}")

    def _validate_semantics(self, deal: DealDefinition, raw_data: Dict[str, Any]):
        errors = []

        # Create Sets for O(1) Lookup
        valid_funds = set(deal.funds.keys())
        valid_accounts = set(deal.accounts.keys())
        valid_variables = set(deal.variables.keys())
        valid_sources = valid_funds.union(valid_accounts)

        # 1. Validate Bond dependencies
        for bond in deal.bonds.values():
            if bond.variable_cap_ref and bond.variable_cap_ref not in valid_variables:
                errors.append(f"Bond '{bond.id}' references undefined variable cap '{bond.variable_cap_ref}'")

        # 2. Validate Waterfalls
        for wf_name, wf_data in raw_data.get('waterfalls', {}).items():
            if 'steps' not in wf_data: continue
            
            for idx, step in enumerate(wf_data['steps']):
                step_ref = f"{wf_name}.Step[{idx+1}] (ID: {step.get('id')})"
                
                # Check Source
                src = step.get('from_fund')
                if src and src not in valid_sources:
                    errors.append(f"{step_ref}: Source '{src}' is not a valid Fund or Account.")
                
                # Check Target (for transfers)
                tgt = step.get('to')
                if step.get('action') == 'TRANSFER_FUND' and tgt:
                    if tgt not in valid_sources:
                        errors.append(f"{step_ref}: Transfer target '{tgt}' is not a valid Fund or Account.")
                
                # Check Unpaid Ledger logic (Simplified)
                # In a full implementation, we would validate 'unpaid_ledger_id' against deal.ledgers

        if errors:
            error_msg = "\n".join(errors)
            logger.error(f"Semantic Validation Failed:\n{error_msg}")
            raise LogicIntegrityError(f"Deal Logic Invalid:\n{error_msg}")
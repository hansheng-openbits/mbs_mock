import pytest
from rmbs_loader import DealLoader, DealLoadError, LogicIntegrityError, SchemaViolationError

# --- TEST DATA FIXTURES ---

@pytest.fixture
def minimal_valid_json():
    return {
        "meta": {"deal_id": "TEST_01", "deal_name": "Test Deal", "asset_type": "NON_AGENCY_RMBS", "version": "1.0"},
        "currency": "USD",
        "dates": {"cutoff_date": "2024-01-01", "payment_frequency": "MONTHLY"}, # shortened for brevity
        "funds": [{"id": "IAF", "description": "Interest Funds"}],
        "accounts": [{"id": "RES", "type": "RESERVE"}],
        "variables": {"NetWAC": "0.05"},
        "bonds": [
            {
                "id": "A1", "type": "NOTE", "original_balance": 100.0,
                "priority": {"interest": 1, "principal": 1},
                "coupon": {"kind": "FIXED", "fixed_rate": 0.04, "variable_cap": "NetWAC"}
            }
        ],
        "waterfalls": {
            "interest": {
                "steps": [
                    {"id": "s1", "from_fund": "IAF", "action": "PAY_BOND_INTEREST", "group": "A"},
                    {"id": "s2", "from_fund": "IAF", "action": "TRANSFER_FUND", "to": "RES"}
                ]
            }
        }
    }

# --- TESTS ---

def test_load_valid_deal(minimal_valid_json):
    loader = DealLoader() # No schema passed, strictly testing logic
    deal = loader.load_from_json(minimal_valid_json)
    
    assert deal.bonds['A1'].original_balance == 100.0
    assert deal.bonds['A1'].variable_cap_ref == "NetWAC"
    assert "IAF" in deal.funds

def test_fail_invalid_source_fund(minimal_valid_json):
    # Break the deal: Reference a fund that doesn't exist
    minimal_valid_json['waterfalls']['interest']['steps'][0]['from_fund'] = "GHOST_FUND"
    
    loader = DealLoader()
    with pytest.raises(LogicIntegrityError) as excinfo:
        loader.load_from_json(minimal_valid_json)
    
    assert "Source 'GHOST_FUND' is not a valid Fund" in str(excinfo.value)

def test_fail_missing_variable_cap(minimal_valid_json):
    # Break the deal: Bond caps on a variable that isn't defined
    del minimal_valid_json['variables']['NetWAC']
    
    loader = DealLoader()
    with pytest.raises(LogicIntegrityError) as excinfo:
        loader.load_from_json(minimal_valid_json)
    
    assert "references undefined variable cap 'NetWAC'" in str(excinfo.value)

def test_fail_bad_enum(minimal_valid_json):
    # Break the deal: Invalid coupon type
    minimal_valid_json['bonds'][0]['coupon']['kind'] = "SUPER_FLOAT"
    
    loader = DealLoader()
    with pytest.raises(SchemaViolationError):
        loader.load_from_json(minimal_valid_json)
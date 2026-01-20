"""
RMBS Platform Unit Tests
========================

This package contains unit tests for the RMBS platform API endpoints
and core functionality.

Test Modules
------------
test_validation
    Tests for /deal/validate and /validation/performance endpoints.
test_scenarios
    Tests for scenario CRUD operations.
test_rbac
    Tests for role-based access control enforcement.
test_audit_bundle
    Tests for audit bundle export functionality.
test_audit_events
    Tests for audit event logging and retrieval.

Running Tests
-------------
Execute all tests with pytest::

    pytest rmbs_platform/unit_tests/ -v

Or run specific test modules::

    pytest rmbs_platform/unit_tests/test_validation.py -v
"""

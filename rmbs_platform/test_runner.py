#!/usr/bin/env python3
"""
Custom Test Runner for RMBS Platform
=====================================

Runs unit tests without pytest dependency.
"""

import sys
import os
import importlib.util
import traceback
from pathlib import Path

def run_test_file(test_file_path):
    """Run a single test file without pytest"""
    print(f'\n📋 Running {test_file_path}...')

    try:
        # Load the test module
        spec = importlib.util.spec_from_file_location('test_module', test_file_path)
        if spec is None or spec.loader is None:
            print(f'❌ Could not load {test_file_path}')
            return False

        test_module = importlib.util.module_from_spec(spec)

        # Mock pytest to avoid import errors
        sys.modules['pytest'] = type('MockPytest', (), {
            'fixture': lambda func=None: func,
            'mark': type('mark', (), {'parametrize': lambda *args, **kwargs: lambda func: func})(),
            'raises': lambda exc: type('ContextManager', (), {'__enter__': lambda self: None, '__exit__': lambda self, *args: None})(),
        })()

        spec.loader.exec_module(test_module)

        # Find test classes and methods
        passed = 0
        failed = 0
        errors = []

        for attr_name in dir(test_module):
            attr = getattr(test_module, attr_name)
            if isinstance(attr, type) and attr_name.startswith('Test'):
                print(f'  🔍 Found test class: {attr_name}')

                # Create instance
                try:
                    instance = attr()
                except Exception as e:
                    print(f'  ❌ Could not instantiate {attr_name}: {e}')
                    failed += 1
                    continue

                # Run test methods
                for method_name in dir(instance):
                    if method_name.startswith('test_'):
                        print(f'    ▶️  Running {method_name}...')
                        try:
                            method = getattr(instance, method_name)
                            method()
                            print(f'    ✅ {method_name}: PASSED')
                            passed += 1
                        except Exception as e:
                            print(f'    ❌ {method_name}: FAILED - {e}')
                            errors.append(f'{attr_name}.{method_name}: {str(e)}')
                            failed += 1

        if failed == 0:
            print(f'✅ {test_file_path}: ALL PASSED ({passed} tests)')
            return True
        else:
            print(f'❌ {test_file_path}: {failed} FAILED, {passed} PASSED')
            for error in errors[:3]:  # Show first 3 errors
                print(f'   {error}')
            return False

    except Exception as e:
        print(f'❌ Error running {test_file_path}: {e}')
        traceback.print_exc()
        return False

def main():
    print('🔍 Running Unit Tests (Custom Runner)')
    print('=' * 60)

    # Add the project root to Python path
    project_root = Path(__file__).resolve().parent
    sys.path.insert(0, str(project_root))

    # Run test files
    test_files = [
        'unit_tests/test_e2e_simulation.py',
        'unit_tests/test_waterfall.py',
        'unit_tests/test_api_integration.py',
        'unit_tests/test_ml_models.py',
        'unit_tests/test_stress_testing.py',
    ]

    results = []
    for test_file in test_files:
        test_path = project_root / test_file
        if test_path.exists():
            success = run_test_file(test_path)
            results.append((test_file, success))
        else:
            print(f'⚠️  {test_file} not found')

    # Summary
    passed_files = sum(1 for _, success in results if success)
    total_files = len(results)

    print('\n' + '=' * 60)
    print(f'📊 SUMMARY: {passed_files}/{total_files} test files passed')
    print('=' * 60)

    return 0 if passed_files == total_files else 1

if __name__ == '__main__':
    sys.exit(main())
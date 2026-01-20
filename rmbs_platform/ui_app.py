"""
RMBS Platform UI - Modular Version
==================================

This is the new modular Streamlit UI that replaces the legacy ui_app.py.
Provides persona-based workflows with modern UX patterns.

Run with: streamlit run ui_app.py
"""

import sys
import os

# Add the current directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

try:
    from ui.app import main

    if __name__ == "__main__":
        main()
except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure you're running this from the rmbs_platform directory")
    print("Usage: cd rmbs_platform && streamlit run ui_app.py")
    sys.exit(1)
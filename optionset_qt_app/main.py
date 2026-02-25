#!/usr/bin/env python
"""
Dataverse OptionSet Helper – Qt Desktop Application
====================================================
Entry point for the PySide6 GUI application.
"""
import sys
import os

# Add parent directory so we can import OptionSetHelper
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from optionset_qt.app import run

if __name__ == "__main__":
    sys.exit(run())

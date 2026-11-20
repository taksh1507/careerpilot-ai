#!/usr/bin/env python3
"""
JobCare Job Scout — CLI entry point.
Usage: python jobcare.py <command> [args]
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from cli.commands import main

if __name__ == "__main__":
    main()

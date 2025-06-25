#!/usr/bin/env python3
"""
Entry point for PyInstaller executable
"""

import sys
from cassandra_analyzer.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
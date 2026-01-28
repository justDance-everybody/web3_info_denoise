"""
Pytest configuration and shared fixtures
"""
import os
import sys

# Add bot directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

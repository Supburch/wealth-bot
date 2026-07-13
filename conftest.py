import sys
import os

# Ensure the project root is on sys.path so that
# `from services.xxx import ...` and `from config import ...` work correctly
# when running pytest from the project root.
sys.path.insert(0, os.path.dirname(__file__))

"""
Root conftest.py - keep the repository import path stable.

Pytest loads this file automatically and adds the repository root to sys.path.
"""
import sys
from pathlib import Path

# Load grpcio before pytest adds nested agent directories to sys.path. The
# requirement_manager package has a local "grpc" package for generated code,
# and early grpcio import prevents third-party imports from resolving to it.
import grpc  # noqa: F401

# Keep the repository root on the Python path.
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

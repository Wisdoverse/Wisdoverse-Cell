"""
Root conftest.py - 确保 Python 路径正确

pytest 会自动加载此文件，将项目根目录加入 sys.path。
"""
import sys
from pathlib import Path

# Load grpcio before pytest adds nested agent directories to sys.path. The
# requirement_manager package has a local "grpc" package for generated code,
# and early grpcio import prevents third-party imports from resolving to it.
import grpc  # noqa: F401

# 确保项目根目录在 Python 路径中
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

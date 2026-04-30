"""
Golden Output Fixtures for Snapshot Testing

Stores expected outputs for deterministic comparison testing.
Used to verify that outputs remain consistent across code changes.
"""
from pathlib import Path

GOLDEN_OUTPUTS_DIR = Path(__file__).parent


def load_golden_output(name: str) -> str:
    """Load a golden output file by name"""
    file_path = GOLDEN_OUTPUTS_DIR / name
    if not file_path.exists():
        raise FileNotFoundError(f"Golden output not found: {name}")
    return file_path.read_text(encoding="utf-8")


def save_golden_output(name: str, content: str) -> None:
    """Save a new golden output file (use during test development)"""
    file_path = GOLDEN_OUTPUTS_DIR / name
    file_path.write_text(content, encoding="utf-8")

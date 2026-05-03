"""Static checks for English-first runtime metadata."""

import re
from pathlib import Path

HAN = re.compile(r"[\u4e00-\u9fff]")
ASSIGNMENT = re.compile(r"(?:agent_name|description)\s*=\s*([\"'])(.*?)\1")
APP_MAIN = tuple(Path(".").glob("**/app/main.py"))
SERVICE_AGENTS = tuple(Path(".").glob("**/service/agent.py"))
API_FILES = tuple(Path(".").glob("**/api/*.py"))
ENGLISH_FIRST_DOCS = (
    Path("AGENTS.md"),
    Path("SPEC.md"),
    Path("README.md"),
    Path("docs"),
    Path("docker-compose.override.cn.yml"),
)


def _candidate_files() -> list[Path]:
    candidates = [*APP_MAIN, *SERVICE_AGENTS, *API_FILES]
    return [
        path
        for path in candidates
        if "tests" not in path.parts
        and ".venv" not in path.parts
        and "node_modules" not in path.parts
    ]


def test_runtime_metadata_is_english_first() -> None:
    offenders: list[str] = []
    for path in _candidate_files():
        text = path.read_text(encoding="utf-8")
        for match in ASSIGNMENT.finditer(text):
            value = match.group(2)
            if HAN.search(value):
                offenders.append(f"{path}:{match.start()}")

    assert offenders == []


def test_docs_and_docker_guidance_are_english_first() -> None:
    offenders: list[str] = []
    for root in ENGLISH_FIRST_DOCS:
        if not root.exists():
            continue
        files = [root] if root.is_file() else list(root.rglob("*.md"))
        for path in files:
            if HAN.search(path.read_text(encoding="utf-8")):
                offenders.append(str(path))

    assert offenders == []

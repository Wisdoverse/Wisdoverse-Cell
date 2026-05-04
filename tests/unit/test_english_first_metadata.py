"""Static checks for English-first runtime metadata."""

import ast
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
    Path(".env.example"),
)
INTERNAL_ENGLISH_FIRST_FILES = (
    Path("shared/capabilities/sync/core/progress.py"),
    Path("shared/capabilities/sync/db/repository.py"),
    Path("agents/requirement_manager/service/__init__.py"),
    Path("shared/messaging/outbound/models/messages.py"),
    Path("shared/tests/test_agent_loop_breaker.py"),
    Path("shared/db/tests/__init__.py"),
    Path("agents/qa_agent/tests/conftest.py"),
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


def _api_route_files() -> list[Path]:
    return [
        path
        for path in API_FILES
        if "tests" not in path.parts
        and ".venv" not in path.parts
        and "node_modules" not in path.parts
    ]


def _literal_parts(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.JoinedStr):
        return [
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
    return []


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


def test_internal_comments_and_docstrings_are_english_first() -> None:
    offenders: list[str] = []
    for path in INTERNAL_ENGLISH_FIRST_FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        for node in [tree, *ast.walk(tree)]:
            if not isinstance(
                node,
                ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
            ):
                continue
            docstring = ast.get_docstring(node)
            if docstring and HAN.search(docstring):
                offenders.append(f"{path}:{getattr(node, 'lineno', 1)}")
        for lineno, line in enumerate(source.splitlines(), start=1):
            comment = line.split("#", 1)[1] if "#" in line else ""
            if HAN.search(comment):
                offenders.append(f"{path}:{lineno}")

    assert offenders == []


def test_onboarding_llm_example_uses_gateway_api() -> None:
    """LLM onboarding must show the real LiteLLM-backed gateway API."""
    text = Path("docs/overview/onboarding.md").read_text(encoding="utf-8")

    assert "llm_gateway.chat" not in text
    assert 'llm_gateway, "chat"' not in text
    assert "await llm_gateway.complete(" in text


def test_api_error_details_are_english_first() -> None:
    offenders: list[str] = []
    for path in _api_route_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg != "detail":
                    continue
                if any(HAN.search(part) for part in _literal_parts(keyword.value)):
                    offenders.append(f"{path}:{keyword.value.lineno}")

    assert offenders == []

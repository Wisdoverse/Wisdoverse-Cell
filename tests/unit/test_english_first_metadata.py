"""Static checks for English-first runtime metadata."""

import ast
import io
import os
import re
import tokenize
from pathlib import Path

HAN = re.compile(r"[\u4e00-\u9fff]")
ASSIGNMENT = re.compile(r"(?:agent_name|description)\s*=\s*([\"'])(.*?)\1")
SKIP_SCAN_DIRS = {
    ".git",
    ".mypy_cache",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}
ENGLISH_FIRST_DOCS = (
    Path("AGENTS.md"),
    Path("SPEC.md"),
    Path("README.md"),
    Path("docs"),
    Path("docker-compose.override.cn.yml"),
    Path(".env.example"),
)

def _repo_files() -> list[Path]:
    files: list[Path] = []
    for root, dirs, names in os.walk("."):
        dirs[:] = [name for name in dirs if name not in SKIP_SCAN_DIRS]
        root_path = Path(root)
        files.extend(root_path / name for name in names)
    return files


def _path_parts(path: Path) -> tuple[str, ...]:
    return tuple(part for part in path.parts if part != ".")


APP_MAIN = tuple(
    path for path in _repo_files() if _path_parts(path)[-2:] == ("app", "main.py")
)
SERVICE_AGENTS = tuple(
    path for path in _repo_files() if _path_parts(path)[-2:] == ("service", "agent.py")
)
API_FILES = tuple(
    path
    for path in _repo_files()
    if len(_path_parts(path)) >= 2
    and _path_parts(path)[-2] == "api"
    and path.suffix == ".py"
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


def _python_code_files() -> list[Path]:
    return [
        path
        for path in _repo_files()
        if path.suffix == ".py"
        and "tests" not in path.parts
        and "fixtures" not in path.parts
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
    for path in _python_code_files():
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
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT and HAN.search(token.string):
                offenders.append(f"{path}:{token.start[0]}")

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

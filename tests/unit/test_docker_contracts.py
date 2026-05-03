"""Static checks for Docker runtime dependency contracts."""

import ast
from pathlib import Path

RUNTIME_REQUIREMENTS = {
    Path("agents/requirement_manager"): Path("agents/requirement_manager/requirements.txt"),
    Path("agents/pjm_agent"): Path("agents/pjm_agent/requirements.txt"),
    Path("agents/dev_agent"): Path("agents/dev_agent/requirements.txt"),
    Path("services/gateways/user_interaction"): Path(
        "services/gateways/user_interaction/requirements.txt"
    ),
    Path("shared/capabilities/analysis"): Path("shared/capabilities/analysis/requirements.txt"),
}


def _imports_llm_gateway(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "shared.infra.llm_gateway":
            return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "shared.infra.llm_gateway":
                    return True
    return False


def test_docker_runtime_units_that_use_llm_gateway_install_litellm() -> None:
    """Canonical Docker targets must include LiteLLM when their runtime uses LLMGateway."""
    for root, requirements_path in RUNTIME_REQUIREMENTS.items():
        uses_llm_gateway = any(
            _imports_llm_gateway(path)
            for path in root.rglob("*.py")
            if "tests" not in path.parts and "__pycache__" not in path.parts
        )
        if not uses_llm_gateway:
            continue

        requirements = requirements_path.read_text(encoding="utf-8")
        assert "litellm" in requirements.lower(), (
            f"{root} imports shared.infra.llm_gateway but {requirements_path} "
            "does not install litellm for its Docker runtime target"
        )

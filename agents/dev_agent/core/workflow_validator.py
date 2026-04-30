"""DAG validation + path whitelist + safety re-scan for generated workflows."""

from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass, field

from shared.evolution.prompt_safety_scanner import PromptSafetyScanner

from ..models.schemas import WorkflowPlan

_PATH_PATTERN = re.compile(r'(?:^|\s)((?:\.\./|/)[^\s"\']+|[a-zA-Z_][\w/.-]*\.\w+)')
_ALLOWED_PREFIXES = ("agents/", "shared/", "tests/", "docs/", ".acceptance/")


@dataclass
class ValidationResult:
    is_valid: bool = True
    violations: list[str] = field(default_factory=list)


class WorkflowValidator:
    def __init__(self, scanner: PromptSafetyScanner | None = None):
        self._scanner = scanner or PromptSafetyScanner()

    def validate(self, plan: WorkflowPlan) -> ValidationResult:
        violations: list[str] = []
        violations.extend(self._check_dag(plan))
        violations.extend(self._check_acceptance_push(plan))

        node_tags: set[str] = set()
        for node in plan.nodes:
            node_tags.update(node.config.get("tags", []))
        if "review" not in node_tags:
            violations.append("Missing 'review' node (quality gate)")
        if "acceptance" not in node_tags:
            violations.append("Missing 'acceptance' node (quality gate)")

        for node in plan.nodes:
            prompt = node.config.get("prompt", "")
            paths = _PATH_PATTERN.findall(prompt)
            for path in paths:
                if path.startswith("..") or path.startswith("/"):
                    violations.append(
                        f"Path traversal in node '{node.name}': {path}"
                    )
                elif "." in path.split("/")[-1]:
                    if not any(path.startswith(p) for p in _ALLOWED_PREFIXES):
                        violations.append(
                            f"Path outside whitelist in node '{node.name}': {path}"
                        )

        for node in plan.nodes:
            prompt = node.config.get("prompt", "")
            if prompt:
                scan_result = self._scanner.scan(prompt)
                if not scan_result.is_safe:
                    for v in scan_result.violations:
                        violations.append(f"Node '{node.name}' prompt: {v}")

        return ValidationResult(
            is_valid=len(violations) == 0, violations=violations
        )

    def _check_acceptance_push(self, plan: WorkflowPlan) -> list[str]:
        if not plan.nodes:
            return []

        last_node = plan.nodes[-1]
        prompt = last_node.config.get("prompt", "")
        lower_prompt = prompt.lower()
        if "git push" not in lower_prompt:
            return [
                f"Final node '{last_node.name}' prompt must include git push"
            ]
        if "dev/wp-" not in lower_prompt:
            return [
                f"Final node '{last_node.name}' must push to dev/wp-<id> branch"
            ]
        return []

    def _check_dag(self, plan: WorkflowPlan) -> list[str]:
        violations: list[str] = []
        node_names = {n.name for n in plan.nodes}

        for node in plan.nodes:
            for dep in node.dependsOn:
                if dep not in node_names:
                    violations.append(
                        f"Node '{node.name}' depends on non-existent '{dep}'"
                    )

        in_degree: dict[str, int] = defaultdict(int)
        graph: dict[str, list[str]] = defaultdict(list)
        for node in plan.nodes:
            in_degree.setdefault(node.name, 0)
            for dep in node.dependsOn:
                graph[dep].append(node.name)
                in_degree[node.name] += 1

        queue = deque(n for n in node_names if in_degree[n] == 0)
        visited = 0
        while queue:
            current = queue.popleft()
            visited += 1
            for neighbor in graph[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if visited < len(node_names):
            violations.append("Cyclic dependency detected in workflow DAG")

        return violations

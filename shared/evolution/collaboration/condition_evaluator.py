"""
Safe Condition Evaluator — Phase 3 Task 3

Uses ast.parse to validate expressions, then manually walks the AST to compute
results. Zero dynamic code execution: no exec, no compile+exec.
"""
import ast
from typing import Any

from shared.utils.logger import get_logger

logger = get_logger("evolution.condition")

# Whitelist of allowed AST node types
_ALLOWED_NODES = {
    ast.Expression,
    ast.Compare,
    ast.BoolOp,
    ast.And,
    ast.Or,
    ast.Gt,
    ast.Lt,
    ast.GtE,
    ast.LtE,
    ast.Eq,
    ast.NotEq,
    ast.Attribute,
    ast.Name,
    ast.Constant,
    ast.Load,  # required for Name/Attribute
}

_ALLOWED_NAMES = {"payload", "null", "true", "false", "None", "True", "False"}


class ConditionEvaluator:
    """Safe expression evaluator for trigger conditions.

    Uses ast.parse to validate, then manually walks the AST to compute results.
    Only allows: comparisons, boolean ops, attribute access on 'payload',
    constants. All other constructs are rejected.
    """

    def validate(self, condition: str) -> tuple[bool, str]:
        """Check whether a condition string is safe to evaluate.

        Returns:
            (True, "") when valid.
            (False, error_message) when invalid or unsafe.
        """
        try:
            tree = ast.parse(condition, mode="eval")
        except SyntaxError as e:
            return False, f"Syntax error: {e}"
        return self._check_node(tree)

    def evaluate(self, condition: str | None, context: dict) -> bool:
        """Evaluate condition against context dict.

        Args:
            condition: Expression string, or None (treated as always-true).
            context:   Dict of variables available during evaluation.
                       Typically {"payload": {...}}.

        Returns:
            Boolean result, or False when condition is invalid / raises.
        """
        if condition is None:
            return True

        is_valid, error = self.validate(condition)
        if not is_valid:
            logger.warning("invalid_condition", condition=condition, error=error)
            return False

        try:
            tree = ast.parse(condition, mode="eval")
            result = self._eval_node(tree.body, context)
            # Coerce to bool; treat None/0/"" as False
            return bool(result) if result is not None else False
        except Exception as e:
            logger.warning(
                "condition_eval_error", condition=condition, error=str(e)
            )
            return False

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_node(self, node: ast.AST) -> tuple[bool, str]:
        """Recursively validate that all AST nodes belong to the whitelist."""
        if type(node) not in _ALLOWED_NODES:
            return False, f"Forbidden node type: {type(node).__name__}"

        # Name nodes: only allowed identifiers
        if isinstance(node, ast.Name) and node.id not in _ALLOWED_NAMES:
            return False, f"Forbidden name: {node.id}"

        # Attribute nodes: no dunder access; only payload.xxx chains
        if isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                return False, f"Forbidden attribute: {node.attr}"

        # Recurse into child nodes
        for child in ast.iter_child_nodes(node):
            ok, err = self._check_node(child)
            if not ok:
                return False, err

        return True, ""

    def _eval_node(self, node: ast.AST, ctx: dict) -> Any:
        """Evaluate a (previously validated) AST node against context."""
        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            if node.id in ("null", "None"):
                return None
            if node.id in ("true", "True"):
                return True
            if node.id in ("false", "False"):
                return False
            return ctx.get(node.id)

        if isinstance(node, ast.Attribute):
            parent = self._eval_node(node.value, ctx)
            if isinstance(parent, dict):
                return parent.get(node.attr)
            return getattr(parent, node.attr, None)

        if isinstance(node, ast.Compare):
            left = self._eval_node(node.left, ctx)
            for op, comparator in zip(node.ops, node.comparators):
                right = self._eval_node(comparator, ctx)
                if not self._compare(left, op, right):
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(self._eval_node(v, ctx) for v in node.values)
            if isinstance(node.op, ast.Or):
                return any(self._eval_node(v, ctx) for v in node.values)

        return False

    @staticmethod
    def _compare(left: Any, op: ast.cmpop, right: Any) -> bool:
        """Apply a single comparison operator."""
        try:
            if isinstance(op, ast.Eq):
                return left == right
            if isinstance(op, ast.NotEq):
                return left != right
            if isinstance(op, ast.Gt):
                return left > right
            if isinstance(op, ast.Lt):
                return left < right
            if isinstance(op, ast.GtE):
                return left >= right
            if isinstance(op, ast.LtE):
                return left <= right
        except TypeError:
            # e.g. None > 0 raises TypeError; treat as False
            return False
        return False

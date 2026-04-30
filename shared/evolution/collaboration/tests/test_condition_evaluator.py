"""
Tests for the Safe Condition Evaluator (Phase 3 Task 3).

Covers:
- evaluate(): None passthrough, numeric/string comparisons, boolean ops
- validate(): security rejections (imports, dunders, calls, subscripts, bare names)
- Edge cases: missing fields, type mismatches
"""

from shared.evolution.collaboration.condition_evaluator import ConditionEvaluator


class TestConditionEvaluator:
    def setup_method(self):
        self.evaluator = ConditionEvaluator()

    # ------------------------------------------------------------------
    # evaluate() — happy path
    # ------------------------------------------------------------------

    def test_none_returns_true(self):
        assert self.evaluator.evaluate(None, {}) is True

    def test_numeric_comparison_true(self):
        ctx = {"payload": {"task_count": 5}}
        assert self.evaluator.evaluate("payload.task_count > 0", ctx) is True

    def test_numeric_comparison_false(self):
        ctx = {"payload": {"task_count": 0}}
        assert self.evaluator.evaluate("payload.task_count > 0", ctx) is False

    def test_string_equality(self):
        ctx = {"payload": {"status": "done"}}
        assert self.evaluator.evaluate('payload.status == "done"', ctx) is True

    def test_string_equality_mismatch(self):
        ctx = {"payload": {"status": "pending"}}
        assert self.evaluator.evaluate('payload.status == "done"', ctx) is False

    def test_not_equal(self):
        ctx = {"payload": {"status": "pending"}}
        assert self.evaluator.evaluate('payload.status != "done"', ctx) is True

    def test_combined_and(self):
        ctx = {"payload": {"items": True, "count": 5}}
        assert (
            self.evaluator.evaluate("payload.items and payload.count > 3", ctx) is True
        )

    def test_combined_and_false(self):
        ctx = {"payload": {"items": False, "count": 5}}
        assert (
            self.evaluator.evaluate("payload.items and payload.count > 3", ctx) is False
        )

    def test_combined_or(self):
        ctx = {"payload": {"a": 0, "b": 1}}
        assert (
            self.evaluator.evaluate("payload.a > 0 or payload.b > 0", ctx) is True
        )

    def test_combined_or_both_false(self):
        ctx = {"payload": {"a": 0, "b": 0}}
        assert (
            self.evaluator.evaluate("payload.a > 0 or payload.b > 0", ctx) is False
        )

    def test_gte_operator(self):
        ctx = {"payload": {"score": 100}}
        assert self.evaluator.evaluate("payload.score >= 100", ctx) is True

    def test_lte_operator(self):
        ctx = {"payload": {"score": 99}}
        assert self.evaluator.evaluate("payload.score <= 100", ctx) is True

    def test_lt_operator(self):
        ctx = {"payload": {"score": 50}}
        assert self.evaluator.evaluate("payload.score < 100", ctx) is True

    def test_boolean_constant_true(self):
        ctx = {"payload": {"flag": True}}
        assert self.evaluator.evaluate("payload.flag == True", ctx) is True

    def test_boolean_constant_false(self):
        ctx = {"payload": {"flag": False}}
        assert self.evaluator.evaluate("payload.flag == False", ctx) is True

    def test_none_constant(self):
        ctx = {"payload": {"field": None}}
        assert self.evaluator.evaluate("payload.field == None", ctx) is True

    # ------------------------------------------------------------------
    # validate() — security rejections
    # ------------------------------------------------------------------

    def test_rejects_import(self):
        # __import__ is a Call node — not in whitelist
        ok, _ = self.evaluator.validate("__import__('os')")
        assert ok is False

    def test_rejects_dunder_attribute(self):
        ok, _ = self.evaluator.validate("payload.__class__")
        assert ok is False

    def test_rejects_dunder_dict(self):
        ok, _ = self.evaluator.validate("payload.__dict__")
        assert ok is False

    def test_rejects_function_call(self):
        ok, _ = self.evaluator.validate("len(payload.items)")
        assert ok is False

    def test_rejects_subscript(self):
        ok, _ = self.evaluator.validate("payload['key']")
        assert ok is False

    def test_rejects_arbitrary_name(self):
        # 'os' is not in _ALLOWED_NAMES
        ok, _ = self.evaluator.validate("os.getcwd()")
        assert ok is False

    def test_rejects_lambda(self):
        ok, _ = self.evaluator.validate("lambda x: x")
        assert ok is False

    def test_rejects_list_comprehension(self):
        ok, _ = self.evaluator.validate("[x for x in payload.items]")
        assert ok is False

    def test_rejects_ifexp(self):
        ok, _ = self.evaluator.validate("1 if True else 0")
        assert ok is False

    def test_rejects_syntax_error(self):
        ok, err = self.evaluator.validate("payload.x ===")
        assert ok is False
        assert "Syntax error" in err

    def test_rejects_unary_op(self):
        ok, _ = self.evaluator.validate("not payload.flag")
        assert ok is False

    def test_rejects_arithmetic(self):
        ok, _ = self.evaluator.validate("payload.count + 1 > 0")
        assert ok is False

    # ------------------------------------------------------------------
    # Edge cases
    # ------------------------------------------------------------------

    def test_missing_field_returns_false_not_crash(self):
        ctx = {"payload": {}}
        # payload.nonexistent returns None; None > 0 raises TypeError → False
        result = self.evaluator.evaluate("payload.nonexistent > 0", ctx)
        assert result is False

    def test_missing_payload_key_returns_false(self):
        ctx = {}
        result = self.evaluator.evaluate("payload.count > 0", ctx)
        assert result is False

    def test_invalid_condition_returns_false(self):
        ctx = {"payload": {"x": 1}}
        result = self.evaluator.evaluate("payload['x'] > 0", ctx)
        assert result is False

    def test_true_literal_constant(self):
        assert self.evaluator.evaluate("True", {}) is True

    def test_false_literal_constant(self):
        assert self.evaluator.evaluate("False", {}) is False

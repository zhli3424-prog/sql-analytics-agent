from __future__ import annotations

import unittest

from scripts.evaluate import HttpFailure, canonical, is_policy_block


class EvaluationTests(unittest.TestCase):
    def test_only_explicit_policy_rejection_counts_as_blocked(self):
        self.assertTrue(is_policy_block(HttpFailure(422, '{"detail":{"message":"请求包含写入意图，已拒绝执行"}}')))
        self.assertFalse(is_policy_block(HttpFailure(503, '{"detail":"模型服务不可用"}')))
        self.assertFalse(is_policy_block(HttpFailure(500, '{"detail":"查询服务暂时不可用"}')))

    def test_result_comparison_ignores_row_order_and_float_noise(self):
        left = canonical(["name", "amount"], [["A", 1.001], ["B", 2.0]])
        right = canonical(["name", "amount"], [["B", 2], ["A", 1.0]])
        self.assertEqual(left, right)


if __name__ == "__main__":
    unittest.main()

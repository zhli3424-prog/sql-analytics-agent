from __future__ import annotations

import unittest
from pathlib import Path

from app.agent import AgentError, choose_chart, validate_question
from app.schema import ALLOWED_TABLES, public_schema
from app.sql_safety import UnsafeSQL, validate_and_limit


class SQLSafetyTests(unittest.TestCase):
    def test_select_and_cte_are_allowed_and_limited(self):
        normalized, executable = validate_and_limit(
            "WITH monthly AS (SELECT date_trunc('month', ordered_at) month FROM analytics.orders) "
            "SELECT month, count(*) FROM monthly GROUP BY month"
        )
        self.assertIn("WITH monthly", normalized)
        self.assertIn("LIMIT 200", executable)

    def test_write_and_multiple_statements_are_rejected(self):
        for sql in (
            "DELETE FROM analytics.orders",
            "SELECT * FROM analytics.orders; SELECT * FROM analytics.customers",
            "UPDATE analytics.orders SET status = 'paid'",
            "DROP TABLE analytics.orders",
        ):
            with self.subTest(sql=sql), self.assertRaises(UnsafeSQL):
                validate_and_limit(sql)

    def test_cross_schema_and_unknown_tables_are_rejected(self):
        for sql in (
            "SELECT * FROM app.query_traces",
            "SELECT * FROM public.users",
            "SELECT * FROM pg_catalog.pg_roles",
        ):
            with self.subTest(sql=sql), self.assertRaises(UnsafeSQL):
                validate_and_limit(sql)

    def test_dangerous_function_is_rejected(self):
        with self.assertRaises(UnsafeSQL):
            validate_and_limit("SELECT pg_sleep(10) FROM analytics.orders LIMIT 1")

    def test_dangerous_question_intent_is_rejected_before_model_call(self):
        for question in (
            "删除所有订单数据",
            "把所有商品价格更新为 1 元",
            "查询 app.query_traces",
            "SELECT * FROM pg_catalog.pg_roles",
        ):
            with self.subTest(question=question), self.assertRaises(AgentError):
                validate_question(question)


class PresentationTests(unittest.TestCase):
    def test_time_series_uses_line_chart(self):
        chart = choose_chart(["month", "gmv"], [["2026-01", 10.0], ["2026-02", 12.0]])
        self.assertEqual(chart["type"], "line")

    def test_category_series_uses_bar_chart(self):
        chart = choose_chart(["category", "gmv"], [["数码", 10.0]])
        self.assertEqual(chart["type"], "bar")

    def test_public_schema_has_only_allowed_tables(self):
        names = {table["name"] for table in public_schema()["tables"]}
        self.assertEqual(names, ALLOWED_TABLES)


class IsolationTests(unittest.TestCase):
    def test_compose_resources_do_not_overlap_rag_project(self):
        compose = (Path(__file__).resolve().parents[1] / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("name: sql-analytics-agent", compose)
        self.assertIn('"8010:8010"', compose)
        self.assertIn("sql-analytics-agent-postgres-data", compose)
        self.assertNotIn("knowledge_agent", compose)
        self.assertNotIn('"8000:8000"', compose)


if __name__ == "__main__":
    unittest.main()

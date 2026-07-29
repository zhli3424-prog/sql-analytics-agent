from __future__ import annotations

import os
import unittest
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal, init_database
from app.importing import replace_dataset
from app.models import Category, Customer, Order, OrderItem, Payment, Product, Refund


@unittest.skipUnless(os.getenv("RUN_DATABASE_TESTS") == "1", "requires a disposable PostgreSQL database")
class DatasetReplaceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_database()

    def test_failed_replacement_rolls_back_to_previous_dataset(self):
        now = datetime(2026, 1, 2, tzinfo=UTC)
        valid = {
            "categories": [{"id": 1, "name": "分类"}],
            "customers": [{"id": 1, "registered_at": date(2026, 1, 1), "region": "华东", "channel": "自然"}],
            "products": [{"id": 1, "category_id": 1, "name": "商品", "unit_cost": Decimal("10"), "list_price": Decimal("20")}],
            "orders": [{"id": 1, "customer_id": 1, "ordered_at": now, "status": "paid", "region": "华东"}],
            "order_items": [{"id": 1, "order_id": 1, "product_id": 1, "quantity": 1, "unit_price": Decimal("20"), "discount_amount": Decimal("0")}],
            "payments": [{"id": 1, "order_id": 1, "method": "微信", "amount": Decimal("20"), "paid_at": now}],
            "refunds": [{"id": 1, "order_id": 1, "amount": Decimal("5"), "reason": "质量问题", "refunded_at": now}],
        }
        with SessionLocal() as session:
            replace_dataset(session, valid)
            session.commit()
            self.assertEqual(session.scalar(select(func.count(Refund.id))), 1)

            invalid = {name: [dict(row) for row in rows] for name, rows in valid.items()}
            invalid["products"][0]["category_id"] = 999
            with self.assertRaises(IntegrityError):
                replace_dataset(session, invalid)
                session.commit()
            session.rollback()

            self.assertEqual(session.scalar(select(Category.name).where(Category.id == 1)), "分类")
            self.assertEqual(session.scalar(select(func.count(Refund.id))), 1)


if __name__ == "__main__":
    unittest.main()

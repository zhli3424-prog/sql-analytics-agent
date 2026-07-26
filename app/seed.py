from __future__ import annotations

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, insert, select

from app.database import SessionLocal
from app.models import Category, Customer, Order, OrderItem, Payment, Product, Refund

CATEGORY_NAMES = ["数码", "家电", "食品", "美妆", "服饰", "家居", "运动", "图书"]
REGIONS = ["华东", "华南", "华北", "西南", "华中", "东北", "西北"]
CHANNELS = ["自然流量", "搜索广告", "短视频", "社交推荐", "线下活动"]
PAYMENT_METHODS = ["支付宝", "微信支付", "银行卡", "数字钱包"]
REFUND_REASONS = ["质量问题", "尺寸不合", "与描述不符", "拍错商品", "物流延迟"]


def seed_if_empty() -> None:
    with SessionLocal() as session:
        if session.scalar(select(func.count(Order.id))) or 0:
            return
        rng = random.Random(20260726)
        today = date.today()

        session.execute(insert(Category), [{"id": i + 1, "name": name} for i, name in enumerate(CATEGORY_NAMES)])
        products = []
        for product_id in range(1, 121):
            category_id = (product_id - 1) % len(CATEGORY_NAMES) + 1
            cost = Decimal(rng.randrange(1500, 180000)) / 100
            price = (cost * Decimal(str(rng.uniform(1.25, 2.2)))).quantize(Decimal("0.01"))
            products.append(
                {
                    "id": product_id,
                    "category_id": category_id,
                    "name": f"{CATEGORY_NAMES[category_id - 1]}商品{product_id:03d}",
                    "unit_cost": cost,
                    "list_price": price,
                }
            )
        session.execute(insert(Product), products)

        customers = [
            {
                "id": customer_id,
                "registered_at": today - timedelta(days=rng.randrange(30, 730)),
                "region": rng.choice(REGIONS),
                "channel": rng.choice(CHANNELS),
            }
            for customer_id in range(1, 10001)
        ]
        bulk_insert(session, Customer, customers)

        orders: list[dict] = []
        items: list[dict] = []
        payments: list[dict] = []
        refunds: list[dict] = []
        item_id = payment_id = refund_id = 1
        statuses = ["paid"] * 12 + ["shipped"] * 20 + ["completed"] * 58 + ["cancelled"] * 10
        product_prices = {row["id"]: row["list_price"] for row in products}

        for order_id in range(1, 50001):
            customer = customers[rng.randrange(len(customers))]
            ordered_at = datetime.now(UTC) - timedelta(
                days=rng.randrange(0, 365), seconds=rng.randrange(0, 86400)
            )
            status = rng.choice(statuses)
            orders.append(
                {
                    "id": order_id,
                    "customer_id": customer["id"],
                    "ordered_at": ordered_at,
                    "status": status,
                    "region": customer["region"],
                }
            )
            total = Decimal("0")
            for _ in range(rng.randint(1, 3)):
                product_id = rng.randint(1, 120)
                quantity = rng.randint(1, 4)
                price = product_prices[product_id]
                discount = (price * quantity * Decimal(str(rng.choice([0, 0, 0, 0.05, 0.1])))).quantize(
                    Decimal("0.01")
                )
                items.append(
                    {
                        "id": item_id,
                        "order_id": order_id,
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit_price": price,
                        "discount_amount": discount,
                    }
                )
                total += price * quantity - discount
                item_id += 1

            if status != "cancelled":
                payments.append(
                    {
                        "id": payment_id,
                        "order_id": order_id,
                        "method": rng.choice(PAYMENT_METHODS),
                        "amount": total.quantize(Decimal("0.01")),
                        "paid_at": ordered_at + timedelta(minutes=rng.randrange(1, 120)),
                    }
                )
                payment_id += 1
                if rng.random() < 0.065:
                    refunds.append(
                        {
                            "id": refund_id,
                            "order_id": order_id,
                            "amount": (total * Decimal(str(rng.uniform(0.2, 1)))).quantize(Decimal("0.01")),
                            "reason": rng.choice(REFUND_REASONS),
                            "refunded_at": ordered_at + timedelta(days=rng.randrange(1, 30)),
                        }
                    )
                    refund_id += 1

        bulk_insert(session, Order, orders)
        bulk_insert(session, OrderItem, items)
        bulk_insert(session, Payment, payments)
        bulk_insert(session, Refund, refunds)
        session.commit()


def bulk_insert(session, model, rows: list[dict], chunk_size: int = 5000) -> None:
    for offset in range(0, len(rows), chunk_size):
        session.execute(insert(model), rows[offset : offset + chunk_size])


if __name__ == "__main__":
    seed_if_empty()


from __future__ import annotations

ALLOWED_TABLES = {
    "categories",
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "refunds",
}

SCHEMA_DESCRIPTION = """
Only query schema analytics.

analytics.categories(id, name)
analytics.customers(id, registered_at, region, channel)
analytics.products(id, category_id, name, unit_cost, list_price)
analytics.orders(id, customer_id, ordered_at, status, region)
analytics.order_items(id, order_id, product_id, quantity, unit_price, discount_amount)
analytics.payments(id, order_id, method, amount, paid_at)
analytics.refunds(id, order_id, amount, reason, refunded_at)

Relationships:
- products.category_id = categories.id
- orders.customer_id = customers.id
- order_items.order_id = orders.id
- order_items.product_id = products.id
- payments.order_id = orders.id
- refunds.order_id = orders.id

Business definitions:
- Valid order: orders.status IN ('paid', 'shipped', 'completed').
- GMV: SUM(order_items.quantity * order_items.unit_price - order_items.discount_amount)
  for valid orders.
- Net sales: GMV minus refunds.amount.
- Average order value: GMV / distinct valid orders.
- Refund rate: refunded order count / distinct valid orders.
- Repeat customer: a customer with at least two valid orders.
- Unless the user asks otherwise, exclude cancelled orders.
""".strip()


def public_schema() -> dict:
    return {
        "schema": "analytics",
        "tables": [
            {"name": "categories", "columns": ["id", "name"]},
            {"name": "customers", "columns": ["id", "registered_at", "region", "channel"]},
            {"name": "products", "columns": ["id", "category_id", "name", "unit_cost", "list_price"]},
            {"name": "orders", "columns": ["id", "customer_id", "ordered_at", "status", "region"]},
            {
                "name": "order_items",
                "columns": ["id", "order_id", "product_id", "quantity", "unit_price", "discount_amount"],
            },
            {"name": "payments", "columns": ["id", "order_id", "method", "amount", "paid_at"]},
            {"name": "refunds", "columns": ["id", "order_id", "amount", "reason", "refunded_at"]},
        ],
        "business_definitions": [
            "有效订单：paid、shipped、completed",
            "GMV：商品数量 × 成交单价 - 优惠金额",
            "净销售额：GMV - 退款金额",
            "复购客户：至少有两笔有效订单",
        ],
    }


from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    registered_at: Mapped[date] = mapped_column(Date)
    region: Mapped[str] = mapped_column(String(40), index=True)
    channel: Mapped[str] = mapped_column(String(40), index=True)


class Product(Base):
    __tablename__ = "products"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("analytics.categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    list_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("analytics.customers.id"), index=True)
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    region: Mapped[str] = mapped_column(String(40), index=True)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("analytics.orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("analytics.products.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("analytics.orders.id"), unique=True)
    method: Mapped[str] = mapped_column(String(30), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = {"schema": "analytics"}

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("analytics.orders.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    reason: Mapped[str] = mapped_column(String(80))
    refunded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class QueryTrace(Base):
    __tablename__ = "query_traces"
    __table_args__ = {"schema": "app"}

    id: Mapped[int] = mapped_column(primary_key=True)
    user_name: Mapped[str | None] = mapped_column(String(80), index=True)
    question: Mapped[str] = mapped_column(Text)
    generated_sql: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    result_columns: Mapped[list[str]] = mapped_column(JSON, default=list)
    result_rows: Mapped[list[list[object]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), index=True)
    execution_ms: Mapped[float | None]
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

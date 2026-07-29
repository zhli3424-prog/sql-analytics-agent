from __future__ import annotations

import io
import zipfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from openpyxl import Workbook

from app.importing import ImportValidationError, parse_dataset_archive, parse_import, validate_rows
from app.main import admin_user


class ImportParsingTests(unittest.TestCase):
    def test_utf8_csv_is_parsed_and_typed(self):
        headers, raw_rows = parse_import("categories.csv", "id,name\n9001,导入测试分类\n".encode())
        rows = validate_rows("categories", headers, raw_rows)
        self.assertEqual(rows, [{"id": 9001, "name": "导入测试分类"}])

    def test_xlsx_is_parsed(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["id", "name"])
        sheet.append([9002, "Excel测试分类"])
        output = io.BytesIO()
        workbook.save(output)
        headers, raw_rows = parse_import("categories.xlsx", output.getvalue())
        rows = validate_rows("categories", headers, raw_rows)
        self.assertEqual(rows[0]["name"], "Excel测试分类")

    def test_unknown_column_and_bad_status_are_rejected(self):
        with self.assertRaises(ImportValidationError):
            validate_rows("categories", ["id", "name", "secret"], [[1, "分类", "x"]])
        headers = ["id", "customer_id", "ordered_at", "status", "region"]
        with self.assertRaises(ImportValidationError):
            validate_rows("orders", headers, [[1, 1, "2026-01-01T00:00:00+00:00", "deleted", "华东"]])

    def test_missing_required_value_is_rejected(self):
        with self.assertRaises(ImportValidationError):
            validate_rows("categories", ["id", "name"], [[1, ""]])

    def test_complete_dataset_zip_is_validated(self):
        samples = {
            "categories.csv": "id,name\n1,分类\n",
            "customers.csv": "id,registered_at,region,channel\n1,2026-01-01,华东,自然\n",
            "products.csv": "id,category_id,name,unit_cost,list_price\n1,1,商品,10,20\n",
            "orders.csv": "id,customer_id,ordered_at,status,region\n1,1,2026-01-02T00:00:00+00:00,paid,华东\n",
            "order_items.csv": "id,order_id,product_id,quantity,unit_price,discount_amount\n1,1,1,1,20,0\n",
            "payments.csv": "id,order_id,method,amount,paid_at\n1,1,微信,20,2026-01-02T00:01:00+00:00\n",
            "refunds.csv": "id,order_id,amount,reason,refunded_at\n",
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for name, content in samples.items():
                archive.writestr(name, content)
        dataset = parse_dataset_archive("dataset.zip", output.getvalue())
        self.assertEqual(list(dataset), [name.removesuffix(".csv") for name in samples])
        self.assertEqual(dataset["refunds"], [])

    def test_incomplete_dataset_zip_is_rejected(self):
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("categories.csv", "id,name\n1,分类\n")
        with self.assertRaises(ImportValidationError):
            parse_dataset_archive("dataset.zip", output.getvalue())


class ImportAuthorizationTests(unittest.TestCase):
    def test_non_admin_is_rejected(self):
        fake = SimpleNamespace(app_role="viewer", admin_import_enabled=True)
        with patch("app.main.settings", fake), self.assertRaises(HTTPException) as caught:
            admin_user("viewer")
        self.assertEqual(caught.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()

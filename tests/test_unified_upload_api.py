import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

import app.api.rules as rules_api
import app.api.uploads as uploads_api
from app.agent.rule_learning.rule_learning_service import RuleLearningPipelineService
from app.agent.rule_learning.rule_repository import RuleRepository
from app.agent.rule_learning.service import RuleLearningService


def _build_sample_xlsx(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Rules"
    ws.append(["品牌", "类别", "匹配规则", "字段映射", "编码段规则", "枚举值", "备注"])
    ws.append(
        [
            "Micron",
            "DDR3",
            r"^PRN(?P<cap>\d+)M8V\w+-\w+$",
            '{"capacity":"group:cap","bus_width":"x8","brand":"Micron"}',
            "prefix:PRN",
            "speed:1600MHz",
            "unit-test",
        ]
    )
    wb.save(path)


class UnifiedUploadApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.xlsx = self.base / "sample.xlsx"
        _build_sample_xlsx(self.xlsx)

        self.repo = RuleRepository(base_dir=str(self.base / "rule_learning"))
        self.learning_service = RuleLearningPipelineService(repo=self.repo)
        self.parse_service = RuleLearningService(repo=self.repo)

        self._old_learning_service = rules_api.learning_service
        self._old_service = rules_api.service
        rules_api.learning_service = self.learning_service
        rules_api.service = self.parse_service

        self._old_doc_handler = uploads_api.handle_document_upload

        app = FastAPI()
        app.include_router(uploads_api.router, prefix="/api/v1")
        self.client = TestClient(app)

    def tearDown(self):
        rules_api.learning_service = self._old_learning_service
        rules_api.service = self._old_service
        uploads_api.handle_document_upload = self._old_doc_handler
        self.tmp.cleanup()

    def test_unified_rules_learn_text_via_json(self):
        resp = self.client.post(
            "/api/v1/uploads/unified",
            json={
                "action": "rules_learn_text",
                "text": "规则: prefix PRN 映射 product_type=DDR 示例 PRN256M8V00HK8DA-12K",
                "source_name": "unified_json_case",
            },
        )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertEqual(data["report"]["source"]["name"], "unified_json_case")

    def test_unified_rules_learn_file_via_multipart(self):
        md_path = self.base / "learn_sample.md"
        md_path.write_text(
            "# 学习样例\n\n规则: prefix PRN 映射 product_type=DDR\n示例: PRN256M8V00HK8DA-12K\n",
            encoding="utf-8",
        )

        with md_path.open("rb") as f:
            resp = self.client.post(
                "/api/v1/uploads/unified",
                data={"action": "rules_learn_file"},
                files={"file": ("learn_sample.md", f, "text/markdown")},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertIn(data["report"]["source"]["input_type"], ["md", "text"])

    def test_unified_rules_import_xlsx(self):
        with self.xlsx.open("rb") as f:
            resp = self.client.post(
                "/api/v1/uploads/unified",
                data={"action": "rules_import_xlsx"},
                files={"file": ("sample.xlsx", f, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertEqual(data["parsed_rows"], 1)

    def test_unified_document_upload_routes_to_document_handler(self):
        async def fake_handle_document_upload(file, category=None):
            return {
                "code": 200,
                "message": "success",
                "filename": file.filename,
                "chunks": 1,
                "vectors": 1,
                "category": category,
            }

        uploads_api.handle_document_upload = fake_handle_document_upload

        txt_path = self.base / "doc.txt"
        txt_path.write_text("hello", encoding="utf-8")

        with txt_path.open("rb") as f:
            resp = self.client.post(
                "/api/v1/uploads/unified",
                data={"action": "document_upload", "category": "demo"},
                files={"file": ("doc.txt", f, "text/plain")},
            )

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertEqual(data["filename"], "doc.txt")
        self.assertEqual(data["category"], "demo")


if __name__ == "__main__":
    unittest.main()

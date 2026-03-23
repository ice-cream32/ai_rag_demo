import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.rules as rules_api
import app.api.uploads as uploads_api
from app.agent.rule_learning.service import RuleLearningService
from app.agent.rule_learning.rule_learning_service import RuleLearningPipelineService
from app.agent.rule_learning.rule_repository import RuleRepository


class RuleLearningPhase6Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)

        self.repo = RuleRepository(base_dir=str(self.base / "rule_learning"))
        self.learning_service = RuleLearningPipelineService(repo=self.repo)

        self._old_learning_service = rules_api.learning_service
        rules_api.learning_service = self.learning_service

        app = FastAPI()
        app.include_router(rules_api.router, prefix="/api/v1")
        app.include_router(uploads_api.router, prefix="/api/v1")
        self.client = TestClient(app)
        self.parse_service = RuleLearningService(repo=self.repo)

    def tearDown(self):
        rules_api.learning_service = self._old_learning_service
        self.tmp.cleanup()

    def test_learning_service_report_structure(self):
        report = self.learning_service.learn_from_text(
            text="规则: prefix PRN 映射 product_type=DDR 示例 PRN256M8V00HK8DA-12K",
            source_name="unit_case",
        )

        self.assertIn("learning_id", report)
        self.assertIn("source", report)
        self.assertIn("pipeline", report)
        self.assertIn("result", report)
        self.assertEqual(report["source"]["input_type"], "text")
        self.assertGreaterEqual(report["pipeline"]["candidates_count"], 0)

    def test_api_unified_learn_from_text_success(self):
        payload = {
            "action": "rules_learn_text",
            "text": "规则: prefix PRN 映射 product_type=DDR 示例 PRN256M8V00HK8DA-12K",
            "source_name": "api_text_case",
        }
        resp = self.client.post("/api/v1/uploads/unified", json=payload)

        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["code"], 200)
        self.assertIn("report", data)
        self.assertEqual(data["report"]["source"]["name"], "api_text_case")

    def test_api_unified_learn_from_text_empty(self):
        resp = self.client.post("/api/v1/uploads/unified", json={"action": "rules_learn_text", "text": "   "})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["code"], 400)

    def test_api_unified_learn_from_file_success(self):
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
        self.assertIn("report", data)
        self.assertIn(data["report"]["source"]["input_type"], ["md", "text"])

    def test_parse_can_use_extension_rule_when_manual_miss(self):
        self.repo.upsert_extension_rule(
            {
                "rule_id": "ext_parse_demo_001",
                "brand": "Micron",
                "category": "DDR3",
                "rule_type": "prefix_match",
                "pattern": {"match_type": "prefix", "value": "PRN"},
                "output": {"product_type": "DDR"},
                "examples": ["PRN256M8V00HK8DA-12K"],
                "source": {
                    "source_type": "text",
                    "file_name": "phase6_unit.txt",
                    "sheet_name": None,
                    "page": None,
                    "raw_text": "prefix PRN => DDR",
                    "chunk_id": "text::phase6::1",
                },
                "confidence": 0.87,
                "status": "candidate",
            }
        )

        result = self.parse_service.parse_local(
            part_number="PRN256M8V00HK8DA-12K",
            brand_hint="Micron",
            enable_web_enrich=False,
        )

        self.assertIsNotNone(result.matched_rule)
        self.assertEqual(result.matched_rule.rule_id, "ext_parse_demo_001")
        self.assertIn("product_type", result.fields)
        self.assertEqual(str(result.fields["product_type"].value), "DDR")
        self.assertEqual(result.fields["product_type"].source, "web_enriched_rule")


if __name__ == "__main__":
    unittest.main()

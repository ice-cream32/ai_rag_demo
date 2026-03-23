import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

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


class RuleLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.xlsx = self.base / "sample.xlsx"
        _build_sample_xlsx(self.xlsx)

        self.repo = RuleRepository(base_dir=str(self.base / "rule_learning"))
        self.service = RuleLearningService(repo=self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_and_list_rules(self):
        report = self.service.import_xlsx(str(self.xlsx))
        self.assertEqual(report.stats.parsed_rows, 1)
        self.assertEqual(report.stats.created_rules, 1)

        listed = self.service.list_rules()
        self.assertEqual(listed.total, 1)
        self.assertEqual(listed.rules[0].brand, "Micron")

    def test_parse_local_prefers_local_rules(self):
        self.service.import_xlsx(str(self.xlsx))
        result = self.service.parse_local(
            part_number="PRN256M8V00HK8DA-12K",
            brand_hint="Micron",
            enable_web_enrich=False,
        )
        self.assertIsNotNone(result.matched_rule)
        self.assertEqual(result.matched_rule.brand, "Micron")
        self.assertIn("capacity", result.fields)
        self.assertEqual(str(result.fields["capacity"].value), "256")
        self.assertEqual(result.fields["capacity"].source, "local_xlsx_rule")


if __name__ == "__main__":
    unittest.main()

"""规则学习服务门面。"""

from __future__ import annotations

from typing import Optional

from app.agent.rule_learning.excel_importer import ExcelRuleImporter
from app.agent.rule_learning.parser import LocalRuleParser
from app.agent.rule_learning.rule_repository import RuleRepository
from app.agent.rule_learning.rule_updater import RuleUpdater
from app.agent.rule_learning.schemas import ImportReport, ParseResult, RuleListResponse


class RuleLearningService:
    def __init__(self, repo: Optional[RuleRepository] = None):
        self.repo = repo or RuleRepository()
        self.importer = ExcelRuleImporter()
        self.rule_updater = RuleUpdater(repo=self.repo)
        self.parser = LocalRuleParser(rule_updater=self.rule_updater)

    def import_xlsx(self, xlsx_path: str) -> ImportReport:
        rules, report = self.importer.import_file(xlsx_path)
        created, updated = self.repo.upsert_manual_rules(rules)
        report.stats.created_rules = created
        report.stats.updated_rules = updated
        self.repo.append_import_log(report)
        return report

    def list_rules(self, brand: Optional[str] = None) -> RuleListResponse:
        return self.repo.list_manual_rules(brand=brand)

    def parse_local(
        self,
        part_number: str,
        brand_hint: Optional[str] = None,
        enable_web_enrich: bool = True,
    ) -> ParseResult:
        rules = self.repo.get_manual_rule_records(brand=brand_hint)
        extension_rules = self.repo.get_extension_rules_raw()
        return self.parser.parse(
            part_number=part_number,
            brand_hint=brand_hint,
            rules=rules,
            extension_rules=extension_rules,
            enable_web_enrich=enable_web_enrich,
        )

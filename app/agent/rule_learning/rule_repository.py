"""规则仓储：分层 JSON 存储。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.agent.rule_learning.schemas import ImportReport, RuleListItem, RuleListResponse, RuleRecord


class RuleRepository:
    def __init__(self, base_dir: str = "./data/rule_learning"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.manual_file = self.base_dir / "manual_rules.json"
        self.import_log_file = self.base_dir / "import_logs.json"
        self.extension_file = self.base_dir / "extension_rules.json"
        self.update_log_file = self.base_dir / "update_logs.json"
        self.conflicts_file = self.base_dir / "conflicts.json"
        self._ensure_layer_files()

    def _ensure_layer_files(self) -> None:
        if not self.extension_file.exists():
            self._save_json(self.extension_file, {"rules": [], "updated_at": None})
        if not self.update_log_file.exists():
            self._save_json(self.update_log_file, {"logs": []})
        if not self.conflicts_file.exists():
            self._save_json(self.conflicts_file, {"items": []})

    def _load_json(self, path: Path, default):
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, path: Path, data) -> None:
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def upsert_manual_rules(self, rules: List[RuleRecord]) -> Tuple[int, int]:
        payload = self._load_json(self.manual_file, {"rules": [], "updated_at": None})
        existing: Dict[str, dict] = {r["rule_id"]: r for r in payload.get("rules", [])}

        created = 0
        updated = 0
        for rule in rules:
            data = rule.model_dump(mode="json")
            if rule.rule_id in existing:
                updated += 1
            else:
                created += 1
            existing[rule.rule_id] = data

        payload["rules"] = list(existing.values())
        payload["updated_at"] = datetime.utcnow().isoformat()
        self._save_json(self.manual_file, payload)
        return created, updated

    def append_import_log(self, report: ImportReport) -> None:
        logs = self._load_json(self.import_log_file, {"logs": []})
        logs["logs"].append(report.model_dump(mode="json"))
        self._save_json(self.import_log_file, logs)

    def get_manual_rules_raw(self) -> List[dict]:
        payload = self._load_json(self.manual_file, {"rules": []})
        return payload.get("rules", [])

    def list_manual_rules(self, brand: Optional[str] = None) -> RuleListResponse:
        payload = self._load_json(self.manual_file, {"rules": []})
        rows = payload.get("rules", [])
        if brand:
            rows = [r for r in rows if (r.get("brand") or "").lower() == brand.lower()]

        items = [
            RuleListItem(
                rule_id=r.get("rule_id", ""),
                brand=r.get("brand", ""),
                category=r.get("category", ""),
                pattern=r.get("pattern", ""),
                source_file=r.get("source_file", ""),
                source_sheet=r.get("source_sheet", ""),
                imported_at=datetime.fromisoformat(r.get("imported_at")),
            )
            for r in rows
            if r.get("imported_at")
        ]

        brands = sorted({i.brand for i in items if i.brand})
        return RuleListResponse(total=len(items), brands=brands, rules=items)

    def get_manual_rule_records(self, brand: Optional[str] = None) -> List[RuleRecord]:
        payload = self._load_json(self.manual_file, {"rules": []})
        rows = payload.get("rules", [])
        if brand:
            rows = [r for r in rows if (r.get("brand") or "").lower() == brand.lower()]

        records: List[RuleRecord] = []
        for r in rows:
            imported_at = r.get("imported_at")
            if not imported_at:
                continue
            try:
                records.append(RuleRecord(**r))
            except Exception:
                # 跳过损坏记录，避免影响整体解析
                continue
        return records

    def upsert_extension_rule(self, rule: dict) -> None:
        payload = self._load_json(self.extension_file, {"rules": [], "updated_at": None})
        existing: Dict[str, dict] = {r.get("rule_id", ""): r for r in payload.get("rules", []) if r.get("rule_id")}
        rule_id = rule.get("rule_id", "")
        if not rule_id:
            return
        existing[rule_id] = rule
        payload["rules"] = list(existing.values())
        payload["updated_at"] = datetime.utcnow().isoformat()
        self._save_json(self.extension_file, payload)

    def get_extension_rules_raw(self) -> List[dict]:
        payload = self._load_json(self.extension_file, {"rules": []})
        return payload.get("rules", [])

    def append_update_log(self, event: dict) -> None:
        logs = self._load_json(self.update_log_file, {"logs": []})
        logs["logs"].append(event)
        self._save_json(self.update_log_file, logs)

    def append_conflicts(self, conflicts: List[dict]) -> None:
        if not conflicts:
            return
        payload = self._load_json(self.conflicts_file, {"items": []})
        payload["items"].extend(conflicts)
        self._save_json(self.conflicts_file, payload)

"""规则学习相关数据模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


RuleSourceType = Literal["local_xlsx_rule", "web_enriched_rule"]


class RuleFieldValue(BaseModel):
    value: Any
    source: RuleSourceType = "local_xlsx_rule"


class RuleRecord(BaseModel):
    rule_id: str
    brand: str = ""
    category: str = ""
    pattern: str = ""
    field_mapping: Dict[str, Any] = Field(default_factory=dict)
    segment_rules: Dict[str, Any] = Field(default_factory=dict)
    enum_values: Dict[str, Any] = Field(default_factory=dict)
    remarks: str = ""
    source_type: RuleSourceType = "local_xlsx_rule"
    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0
    imported_at: datetime


class ImportStats(BaseModel):
    total_rows: int = 0
    parsed_rows: int = 0
    skipped_rows: int = 0
    updated_rules: int = 0
    created_rules: int = 0
    by_brand: Dict[str, int] = Field(default_factory=dict)


class ImportWarning(BaseModel):
    sheet: str
    row: int
    message: str


class ImportReport(BaseModel):
    source_file: str
    imported_at: datetime
    sheets: List[str] = Field(default_factory=list)
    stats: ImportStats
    warnings: List[ImportWarning] = Field(default_factory=list)


class RuleListItem(BaseModel):
    rule_id: str
    brand: str
    category: str
    pattern: str
    source_file: str
    source_sheet: str
    imported_at: datetime


class RuleListResponse(BaseModel):
    total: int
    brands: List[str] = Field(default_factory=list)
    rules: List[RuleListItem] = Field(default_factory=list)


class ParseRequest(BaseModel):
    part_number: str
    brand_hint: Optional[str] = None
    enable_web_enrich: bool = True


class ParsedField(BaseModel):
    value: Any
    source: RuleSourceType = "local_xlsx_rule"
    rule_id: str = ""


class MatchedRuleInfo(BaseModel):
    rule_id: str
    source_type: RuleSourceType = "local_xlsx_rule"
    brand: str = ""
    category: str = ""
    pattern: str = ""


class ParseResult(BaseModel):
    part_number: str
    fields: Dict[str, ParsedField] = Field(default_factory=dict)
    matched_rule: Optional[MatchedRuleInfo] = None
    images: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    notes: List[str] = Field(default_factory=list)

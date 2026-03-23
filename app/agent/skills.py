"""智能体技能：基于 LangChain @tool 的料号解析与知识检索。"""

import json
import logging
import re
from typing import Any, Dict, List, Tuple

from langchain_core.tools import tool

from app.agent.rule_learning import RuleLearningService
from app.agent.rule_learning.web_enricher import WebEnricher
from app.agent.part_number_parser import PartNumberParser

logger = logging.getLogger(__name__)

_parser = PartNumberParser()
_rule_learning_service = RuleLearningService()
_web_enricher = WebEnricher()


# ====================================================================
# 辅助函数（内部使用，不暴露为 tool）
# ====================================================================

def _clean_value(value: Any, default: str = "X") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text in {"N/A", "无", "未知", "未知品牌", "-"}:
        return default
    return text


def _extract_percent(text: str) -> str:
    value = _clean_value(text)
    if value == "X":
        return "X"
    match = re.search(r"(\d+(?:\.\d+)?)%", value)
    return f"{match.group(1)}%" if match else "X"


def _capacity_to_gb(text: str) -> float | None:
    value = _clean_value(text)
    if value == "X":
        return None
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)([TGMK])B?", value.upper())
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    mapping = {
        "T": 1024.0,
        "G": 1.0,
        "M": 1 / 1024,
        "K": 1 / (1024 * 1024),
    }
    return amount * mapping[unit]


def _normalize_ball_count(value: str) -> str:
    text = _clean_value(value)
    if text == "X":
        return text
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else text


def _normalize_layers(value: str) -> str:
    text = _clean_value(value)
    if text == "X":
        return text
    match = re.search(r"(\d+)", text)
    return match.group(1) if match else text


def _normalize_type(value: str, ddr_type: str) -> str:
    product_type = _clean_value(value)
    tech = _clean_value(ddr_type)
    if product_type == "X":
        return product_type
    if product_type == "DDR 颗粒" and tech != "X":
        return f"{tech}颗粒"
    return product_type.replace("NAND FLASH ", "NAND").replace(" ", "")


def _normalize_frequency(value: str) -> str:
    text = _clean_value(value)
    if text == "X":
        return text
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return match.group(1) if match else text


def _parse_part_number(part_number: str) -> Dict[str, str]:
    raw = _parser.parse(part_number.strip().upper())
    details = raw.get("解析结果", {}) if isinstance(raw, dict) else {}
    standard = _clean_value(raw.get("标准格式"), "")
    standard_parts = [part.strip() for part in standard.split(",")] if standard else []

    def std(index: int) -> str:
        if 0 <= index < len(standard_parts):
            return _clean_value(standard_parts[index])
        return "X"

    grade = _clean_value(details.get("良率/等级"))
    return {
        "part_number": part_number.strip().upper(),
        "brand_cn": _clean_value(details.get("品牌"), std(1) if std(1) != "X" else "X"),
        "brand_code": _clean_value(details.get("品牌代码")),
        "product_type": std(0) if std(0) != "X" else _normalize_type(details.get("产品类型"), details.get("DDR 代数")),
        "capacity_string": _clean_value(details.get("容量字符串")),
        "die_model": _clean_value(details.get("晶圆型号")),
        "die_capacity": _clean_value(details.get("晶圆容量")),
        "chip_capacity": std(2) if std(2) != "X" else _clean_value(details.get("容量")),
        "stacking_layers": _normalize_layers(std(8) if std(8) != "X" else details.get("叠层")),
        "process_node": std(3) if std(3) != "X" else _clean_value(details.get("制程")),
        "bit_width": std(4) if std(4) != "X" else _clean_value(details.get("位宽")),
        "ball_count": _normalize_ball_count(std(5) if std(5) != "X" else details.get("球位")),
        "die_grade": std(6) if std(6) != "X" else grade,
        "chip_grade": std(6) if std(6) != "X" else grade,
        "ddr_frequency": _normalize_frequency(std(7) if std(7) != "X" else details.get("频率")),
        "technology_type": _clean_value(details.get("DDR 代数")),
        "standard_format": standard,
        "capacity_formula": _clean_value(details.get("容量计算"), ""),
    }


def _compute_parameters(part_number: str, quantity: int = 1) -> Dict[str, str]:
    result = _parse_part_number(part_number)
    qty = max(int(quantity), 0)
    chip_gb = _capacity_to_gb(result.get("chip_capacity", "X"))
    total_gb = chip_gb * qty if chip_gb is not None else None
    total_tb = total_gb / 1024 if total_gb is not None else None
    yield_text = _extract_percent(_get_grade(result))
    yield_value = float(yield_text[:-1]) if yield_text != "X" else None
    good_output = total_gb * yield_value / 100 if total_gb is not None and yield_value is not None else None

    return {
        **result,
        "quantity": str(qty),
        "capacity_per_piece_gb": f"{chip_gb:.3f}" if chip_gb is not None else "X",
        "total_capacity_gb": f"{total_gb:.3f}" if total_gb is not None else "X",
        "total_capacity_tb": f"{total_tb:.3f}" if total_tb is not None else "X",
        "yield_percent": yield_text,
        "good_output_gb": f"{good_output:.3f}" if good_output is not None else "X",
    }


def _build_bom_rows(items: List[Tuple[str, int]]) -> Dict[str, Any]:
    rows: List[Dict[str, str]] = []
    total_capacity_gb = 0.0
    total_good_output_gb = 0.0

    for part_number, quantity in items:
        row = _compute_parameters(part_number, quantity)
        rows.append(row)
        if row["total_capacity_gb"] != "X":
            total_capacity_gb += float(row["total_capacity_gb"])
        if row["good_output_gb"] != "X":
            total_good_output_gb += float(row["good_output_gb"])

    return {
        "rows": rows,
        "summary": {
            "item_count": len(rows),
            "total_capacity_gb": f"{total_capacity_gb:.3f}",
            "total_capacity_tb": f"{(total_capacity_gb / 1024):.3f}",
            "total_good_output_gb": f"{total_good_output_gb:.3f}",
            "total_good_output_tb": f"{(total_good_output_gb / 1024):.3f}",
        },
    }


def _get_grade(result: dict) -> str:
    grade = result.get("chip_grade", "X")
    if grade == "X":
        grade = result.get("die_grade", "X")
    return grade


def _format_part_table(result: dict) -> str:
    grade = _get_grade(result)
    return (
        "|品牌名称|晶圆型号|晶圆容量|颗粒容量|位宽|制程|球位|良率|叠代|\n"
        "|----|----|----|----|----|----|----|----|----|\n"
        f"|{result.get('brand_cn', 'X')}|{result.get('die_model', 'X')}|{result.get('die_capacity', 'X')}|"
        f"{result.get('chip_capacity', 'X')}|{result.get('bit_width', 'X')}|{result.get('process_node', 'X')}|"
        f"{result.get('ball_count', 'X')}|{grade}|{result.get('stacking_layers', 'X')}|\n"
    )


# ====================================================================
# 智能体技能（LangChain 工具）
# ====================================================================

@tool
def query_part_number(part_number: str) -> str:
    """解析单个存储芯片料号，返回品牌、晶圆型号、容量、位宽、制程、球位、良率等参数表格。
    输入：料号字符串，如 FBMB47R128G8ABAEAWG5-AS"""
    try:
        result = _parse_part_number(part_number.strip())
        table = _format_part_table(result)
        standard = result.get("standard_format", "")
        if standard:
            return f"{table}\n标准格式：{standard}"
        return table
    except Exception as e:
        return f"解析失败：{str(e)}"


@tool
def calculate_chip_parameters(part_number: str, quantity: int = 1) -> str:
    """计算存储芯片的扩展参数，包括总容量、良品产出等。
    输入：part_number - 料号字符串，quantity - 数量（默认1）"""
    try:
        result = _compute_parameters(part_number.strip(), quantity=quantity)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"参数计算失败：{str(e)}"


@tool
def compare_part_numbers(part_numbers: List[str]) -> str:
    """对比多个存储芯片料号的参数差异。输入：料号列表，至少2个。"""
    try:
        if len(part_numbers) < 2:
            return "对比失败：至少提供2个料号"
        cleaned = [pn.strip().upper() for pn in part_numbers]
        rows = [_compute_parameters(pn, quantity=1) for pn in cleaned]
        lines = [
            "|料号|品牌|类型|晶圆型号|晶圆容量|颗粒容量|位宽|球位|频率|良率|叠层|",
            "|----|----|----|----|----|----|----|----|----|----|----|",
        ]
        for idx, row in enumerate(rows):
            pn = cleaned[idx]
            grade = _get_grade(row)
            lines.append(
                f"|{pn}|{row.get('brand_cn', 'X')}|{row.get('product_type', 'X')}|{row.get('die_model', 'X')}|"
                f"{row.get('die_capacity', 'X')}|{row.get('chip_capacity', 'X')}|{row.get('bit_width', 'X')}|"
                f"{row.get('ball_count', 'X')}|{row.get('ddr_frequency', 'X')}|{grade}|{row.get('stacking_layers', 'X')}|"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"对比失败：{str(e)}"


@tool
def generate_bom(items: List[dict]) -> str:
    """生成 BOM（物料清单），计算总容量和有效产出。
    输入：items 列表，每项包含 part_number（料号）和 quantity（数量）。
    示例：[{"part_number": "FBMB47R128G8...", "quantity": 100}]"""
    try:
        parsed_items = []
        for item in items:
            pn = str(item.get("part_number", "")).strip().upper()
            qty = int(item.get("quantity", 0))
            if pn and qty > 0:
                parsed_items.append((pn, qty))
        if not parsed_items:
            return "BOM生成失败：未提供有效 items"

        bom = _build_bom_rows(parsed_items)
        lines = [
            "|料号|数量|品牌|类型|颗粒容量|单颗(GB)|总容量(GB)|良率|有效产出(GB)|",
            "|----|----|----|----|----|----|----|----|----|",
        ]
        for row in bom["rows"]:
            grade = _get_grade(row)
            lines.append(
                f"|{row.get('brand_code', 'X')}:{row.get('die_model', 'X')}|{row.get('quantity', '0')}|{row.get('brand_cn', 'X')}|"
                f"{row.get('product_type', 'X')}|{row.get('chip_capacity', 'X')}|{row.get('capacity_per_piece_gb', 'X')}|"
                f"{row.get('total_capacity_gb', 'X')}|{grade}|{row.get('good_output_gb', 'X')}|"
            )
        summary = bom["summary"]
        lines.append("")
        lines.append("**BOM汇总**")
        lines.append(f"- 项目数: {summary['item_count']}")
        lines.append(f"- 总容量: {summary['total_capacity_gb']} GB ({summary['total_capacity_tb']} TB)")
        lines.append(f"- 有效产出: {summary['total_good_output_gb']} GB ({summary['total_good_output_tb']} TB)")
        return "\n".join(lines)
    except Exception as e:
        return f"BOM生成失败：{str(e)}"


@tool
def search_knowledge_base(query: str) -> str:
    """在半导体知识库中检索相关技术文档。当用户询问半导体技术知识、产品规格、行业资讯等文档类问题时使用此工具。
    输入：用户的问题或关键词"""
    try:
        from app.retriever import get_vector_retriever
        from app.config import get_settings

        settings = get_settings()
        retriever = get_vector_retriever()
        docs = retriever.retrieve(query, k=settings.rag_top_k * 2)

        # 过滤低相似度
        filtered = [(s, t, m) for s, t, m in docs if s >= settings.rag_min_similarity]
        top_docs = filtered[:settings.rag_top_k]

        if not top_docs:
            return "知识库中没有找到相关文档。"

        formatted = []
        for i, (score, text, metadata) in enumerate(top_docs, 1):
            source = metadata.get("source", "未知来源")
            formatted.append(f"[文档 {i}] (来源: {source}, 相关度: {score:.3f})\n{text}")

        return "\n\n".join(formatted)
    except Exception as e:
        logger.error(f"知识库检索失败: {e}")
        return f"知识库检索失败：{str(e)}"


@tool
def search_web_for_part_number(part_number: str, brand_hint: str = "") -> str:
    """联网搜索料号相关网页、字段线索和图片候选。
    输入：part_number（必填），brand_hint（可选）。"""
    try:
        result = _web_enricher.enrich(
            part_number=part_number.strip().upper(),
            brand_hint=brand_hint.strip() or None,
        )
        return json.dumps(
            {
                "part_number": part_number.strip().upper(),
                "brand_hint": brand_hint.strip(),
                "fields": result.get("fields", {}),
                "field_sources": result.get("field_sources", {}),
                "pages": result.get("pages", []),
                "images": result.get("images", []),
            },
            ensure_ascii=False,
            indent=2,
        )
    except Exception as e:
        logger.error(f"联网搜索失败: {e}", exc_info=True)
        return f"联网搜索失败：{str(e)}"


@tool
def parse_part_number_rule_learning(
    part_number: str,
    brand_hint: str = "",
    enable_web_enrich: bool = True,
) -> str:
    """基于规则学习系统解析料号：本地规则优先，缺失字段可联网补全。
    输入：part_number（必填），brand_hint（可选），enable_web_enrich（默认 true）。"""
    try:
        result = _rule_learning_service.parse_local(
            part_number=part_number,
            brand_hint=brand_hint or None,
            enable_web_enrich=enable_web_enrich,
        )
        return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"规则学习解析失败: {e}", exc_info=True)
        return f"规则学习解析失败：{str(e)}"


def get_all_tools():
    """返回所有 Agent Skills（LangChain Tool 列表）"""
    return [
        search_web_for_part_number,
        search_knowledge_base,
        parse_part_number_rule_learning,
    ]

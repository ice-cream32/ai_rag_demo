"""Generate an example xlsx for rule learning import."""

from pathlib import Path

from openpyxl import Workbook


def main() -> None:
    out_dir = Path("data/rule_learning/examples")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "rule_learning_example.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = "BrandRules"

    ws.append(["规则ID", "品牌", "类别", "匹配规则", "字段映射", "编码段规则", "枚举值", "备注"])
    ws.append([
        "micron_ddr3_rule_v1",
        "Micron",
        "DDR3",
        r"^PRN(?P<capacity>\d+)M8V(?P<wafer>[A-Z0-9]+)-(?P<suffix>[A-Z0-9]+)$",
        '{"brand":"Micron","capacity":"group:capacity","bus_width":"x8"}',
        "prefix:PRN; suffix:12K=1600MHz",
        "grade:SLC/MLC/TLC",
        "Micron DDR3 sample",
    ])
    ws.append([
        "samsung_lpddr4_rule_v1",
        "Samsung",
        "LPDDR4",
        r"^K4(?P<series>[A-Z0-9]+)$",
        '{"brand":"Samsung","category":"LPDDR4"}',
        "prefix:K4",
        "temperature:commercial/industrial",
        "Samsung LPDDR4 sample",
    ])

    wb.save(out_file)
    print(f"generated: {out_file}")


if __name__ == "__main__":
    main()

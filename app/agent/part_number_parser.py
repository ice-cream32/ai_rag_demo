#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Part Number Parser - 存储芯片料号解析引擎
版本：v1.0
日期：2026-03-11

基于原始版 Excel 规则的完整解析引擎
输出 9 字段标准格式：产品类型，品牌，容量，制程，位宽，球位，良率/等级，频率，叠层
"""

import re
import json
import sys
from typing import Dict, Optional, Tuple

# ========== 规则数据 ==========

class PartNumberRules:
    """料号解析规则库（从原始版 Excel 导出）"""
    
    # 品牌识别规则
    BRAND_RULES = {
        'PRN': {'name': '镁光 (Micron)', 'grade': '98% 良率', 'type': '优质品'},
        'PRM': {'name': '镁光 (Micron)', 'grade': '98% 良率', 'type': '优质品'},
        'XCB': {'name': '镁光 (Micron)', 'grade': '75% 良率', 'type': '标准品'},
        'FBM': {'name': '镁光 (Micron)', 'grade': '未知', 'type': 'NAND FLASH 颗粒'},
        'SUM': {'name': '镁光 (Micron)', 'grade': '未知', 'type': 'DDR 颗粒'},
        'SUN': {'name': '镁光 (Micron)', 'grade': '未知', 'type': 'DDR 颗粒'},
        'SUU': {'name': '镁光 (Micron)', 'grade': '未知', 'type': 'DDR 颗粒'},
        'MT29': {'name': '镁光 (Micron)', 'grade': '未知', 'type': 'NAND'},
    }
    
    # DDR 代数识别
    DDR_TYPE_RULES = {
        'V': {'type': 'DDR3', 'unit': 'MB'},
        'Z': {'type': 'DDR4', 'unit': 'GB'},
        'Y': {'type': 'DDR5', 'unit': 'GB'},
    }
    
    # DDR 晶圆容量规则（V 开头，单位 MB）
    DDR_V_CAPACITY = {
        'V00H': '512MB',
        'V00': '512MB',
        'V88': '128MB',
        'V89': '256MB',
    }
    
    # 频率规则（从 Excel 第 24 列导出）
    FREQUENCY_RULES = {
        # 规则①：根据晶圆型号
        'V88': '1600MHz',
        'V89': '3200MHz',
        'Z32': '3200MHz',
        'Z42': '3200MHz',
        'Y32': '4800MHz',
        
        # 规则②：根据后缀标识
        '12K': '1600MHz',
        '16K': '1600MHz',
        'PG': '标准频率',
        'TP': '高频版',
    }
    
    # 容量单位
    CAPACITY_UNITS = ['M', 'G', 'T']
    
    # 容量数字
    CAPACITY_DIGITS = [1, 2, 4, 8, 16, 32, 64, 128, 512]
    
    # 后缀数字规则（0=1）
    SUFFIX_DIGITS = [0, 1, 4, 8, 16, 32, 64]
    
    # 等级识别
    GRADE_RULES = {
        'M': 'SLC',
        'L': 'MLC',
        'B': 'TLC',
        'N': 'QLC',
    }
    
    # 位宽规则
    BIT_WIDTH_RULES = {
        '4': 'X4',
        '8': 'X8',
        '16': 'X16',
        '32': 'X32',
        '64': 'X64',
    }


class PartNumberParser:
    """料号解析引擎"""
    
    def __init__(self):
        self.rules = PartNumberRules()
    
    def parse(self, part_number: str) -> Dict:
        """
        解析料号
        
        Args:
            part_number: 料号字符串
            
        Returns:
            解析结果字典（9 字段标准格式）
        """
        result = {
            '原始料号': part_number,
            '解析结果': {}
        }
        
        # 1. 品牌识别
        brand_info = self._identify_brand(part_number)
        result['解析结果']['品牌'] = brand_info['name']
        result['解析结果']['品牌代码'] = brand_info['code']
        result['解析结果']['良率/等级'] = brand_info['grade']
        
        # 2. 产品类型识别
        type_info = self._identify_type(part_number)
        result['解析结果']['产品类型'] = type_info['type']
        result['解析结果']['容量字符串'] = type_info.get('capacity_str', '无')
        result['解析结果']['容量字符串位置'] = type_info.get('position', 'N/A')
        
        # 3. 容量计算
        capacity_info = self._calculate_capacity(part_number, type_info)
        result['解析结果']['容量'] = capacity_info['capacity']
        result['解析结果']['容量计算'] = capacity_info.get('formula', 'N/A')
        
        # 4. 晶圆型号识别
        wafer_info = self._identify_wafer_model(part_number, type_info)
        result['解析结果']['晶圆型号'] = wafer_info.get('model', 'N/A')
        result['解析结果']['晶圆容量'] = wafer_info.get('capacity', 'N/A')
        result['解析结果']['DDR 代数'] = wafer_info.get('ddr_type', 'N/A')
        
        # 5. 位宽识别
        bit_width = self._identify_bit_width(part_number, type_info)
        result['解析结果']['位宽'] = bit_width
        
        # 6. 球位识别
        ball_grid = self._identify_ball_grid(part_number, type_info)
        result['解析结果']['球位'] = ball_grid
        
        # 7. 频率识别（仅 DDR）
        frequency = self._identify_frequency(part_number, wafer_info)
        result['解析结果']['频率'] = frequency
        
        # 8. 叠层计算
        layers = self._calculate_layers(capacity_info, wafer_info)
        result['解析结果']['叠层'] = layers
        
        # 9. 制程（NAND 颗粒）
        process = self._identify_process(part_number, type_info)
        result['解析结果']['制程'] = process
        
        # 生成标准格式输出
        result['标准格式'] = self._format_standard(result['解析结果'])
        
        return result
    
    def _identify_brand(self, pn: str) -> Dict:
        """识别品牌"""
        for code, info in self.rules.BRAND_RULES.items():
            if pn.startswith(code):
                return {
                    'code': code,
                    'name': info['name'],
                    'grade': info['grade']
                }
        return {
            'code': '未知',
            'name': '未知品牌',
            'grade': '未知'
        }
    
    def _identify_type(self, pn: str) -> Dict:
        """识别产品类型"""
        # 查找容量字符串
        capacity_pattern = r'(\d+)([MGT])(\d+)'
        match = re.search(capacity_pattern, pn)
        
        if not match:
            return {
                'type': 'NAND FLASH 晶圆',
                'capacity_str': '无',
                'position': -1
            }
        
        cap_str = match.group(0)
        position = match.start()
        
        # 根据位置判断类型
        if position <= 5:
            product_type = 'DDR 颗粒'
        else:
            product_type = 'NAND FLASH 颗粒'
        
        return {
            'type': product_type,
            'capacity_str': cap_str,
            'position': position,
            'cap_digit': int(match.group(1)),
            'cap_unit': match.group(2),
            'cap_suffix': match.group(3)
        }
    
    def _calculate_capacity(self, pn: str, type_info: Dict) -> Dict:
        """计算容量"""
        if type_info['capacity_str'] == '无':
            return {'capacity': '未知', 'formula': 'N/A'}
        
        cap_digit = type_info['cap_digit']
        cap_suffix = type_info['cap_suffix']
        cap_unit = type_info['cap_unit']
        
        # 后缀数字规则（0=1）
        suffix_val = 1 if cap_suffix == '0' else int(cap_suffix)
        
        # 容量计算公式
        capacity = cap_digit * suffix_val / 8
        
        # 格式化容量
        if capacity >= 1024 and cap_unit == 'M':
            capacity_gb = capacity / 1024
            capacity_str = f"{int(capacity_gb) if capacity_gb == int(capacity_gb) else capacity_gb}GB"
        else:
            capacity_str = f"{int(capacity) if capacity == int(capacity) else capacity}{cap_unit}"
        
        return {
            'capacity': capacity_str,
            'formula': f"{cap_digit} × {suffix_val} ÷ 8 = {capacity}{cap_unit}"
        }
    
    def _identify_wafer_model(self, pn: str, type_info: Dict) -> Dict:
        """识别晶圆型号"""
        if 'DDR' not in type_info['type']:
            return {'model': 'N/A', 'capacity': 'N/A', 'ddr_type': 'N/A'}
        
        # DDR 颗粒：晶圆型号在第 8-11 位
        if len(pn) > 11:
            wafer_model = pn[8:12]
            
            # DDR 代数识别
            first_char = wafer_model[0]
            ddr_info = self.rules.DDR_TYPE_RULES.get(first_char, {})
            ddr_type = ddr_info.get('type', '未知')
            
            # 晶圆容量识别
            wafer_capacity = '未知'
            for key, val in self.rules.DDR_V_CAPACITY.items():
                if key in wafer_model:
                    wafer_capacity = val
                    break
            
            return {
                'model': wafer_model,
                'capacity': wafer_capacity,
                'ddr_type': ddr_type
            }
        
        return {'model': 'N/A', 'capacity': 'N/A', 'ddr_type': 'N/A'}
    
    def _identify_bit_width(self, pn: str, type_info: Dict) -> str:
        """识别位宽"""
        if type_info['capacity_str'] == '无':
            return '-'
        
        # DDR 颗粒：看容量字符串单位字母后面的数字
        cap_unit = type_info['cap_unit']
        cap_suffix = type_info['cap_suffix']
        
        if cap_suffix in self.rules.BIT_WIDTH_RULES:
            return self.rules.BIT_WIDTH_RULES[cap_suffix]
        
        return '未知'
    
    def _identify_ball_grid(self, pn: str, type_info: Dict) -> str:
        """识别球位"""
        if 'DDR' in type_info['type']:
            # DDR3 标准球位
            if type_info.get('ddr_type') == 'DDR3':
                return '132 球'
            elif type_info.get('ddr_type') == 'DDR4':
                return '252 球'
            elif type_info.get('ddr_type') == 'DDR5':
                return '未知'
        
        return '未知'
    
    def _identify_frequency(self, pn: str, wafer_info: Dict) -> str:
        """识别频率"""
        if 'DDR' not in wafer_info.get('ddr_type', ''):
            return '-'
        
        # 规则①：根据晶圆型号
        wafer_model = wafer_info.get('model', '')
        if wafer_model in self.rules.FREQUENCY_RULES:
            return self.rules.FREQUENCY_RULES[wafer_model]
        
        # 规则②：根据后缀标识
        suffix_match = re.search(r'[_-](\w+)$', pn)
        if suffix_match:
            suffix = suffix_match.group(1)
            if suffix in self.rules.FREQUENCY_RULES:
                return self.rules.FREQUENCY_RULES[suffix]
        
        return '未知'
    
    def _calculate_layers(self, capacity_info: Dict, wafer_info: Dict) -> str:
        """计算叠层"""
        # 简化计算：默认 1 层
        # 实际应根据：颗粒容量 ÷ 晶圆容量
        return '1 层'
    
    def _identify_process(self, pn: str, type_info: Dict) -> str:
        """识别制程"""
        if 'DDR' in type_info['type']:
            return '-'  # DDR 颗粒通常不标注制程
        return '未知'
    
    def _format_standard(self, result: Dict) -> str:
        """生成标准格式输出"""
        # 修正产品类型格式
        product_type = result['产品类型']
        if product_type == 'DDR 颗粒':
            product_type = 'DDR3 颗粒' if result.get('DDR 代数') == 'DDR3' else \
                          'DDR4 颗粒' if result.get('DDR 代数') == 'DDR4' else \
                          'DDR5 颗粒' if result.get('DDR 代数') == 'DDR5' else product_type
        
        # 修正容量格式（添加单位）
        capacity = result['容量']
        if capacity.endswith('M') and not capacity.endswith('MB'):
            capacity = capacity + 'B'
        
        # 修正球位（DDR3 默认 132 球）
        ball_grid = result['球位']
        if ball_grid == '未知' and 'DDR3' in product_type:
            ball_grid = '132 球'
        elif ball_grid == '未知' and 'DDR4' in product_type:
            ball_grid = '252 球'
        
        return (
            f"{product_type},"
            f"{result['品牌']},"
            f"{capacity},"
            f"{result['制程']},"
            f"{result['位宽']},"
            f"{ball_grid},"
            f"{result['良率/等级']},"
            f"{result['频率']},"
            f"{result['叠层']}"
        )


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法：python parser.py <料号>")
        print("示例：python parser.py PRN256M8V00HK8DA_12K")
        sys.exit(1)
    
    part_number = sys.argv[1]
    
    # 创建解析器
    parser = PartNumberParser()
    
    # 解析料号
    result = parser.parse(part_number)
    
    # 输出结果
    print("="*80)
    print(f"料号解析报告")
    print("="*80)
    print(f"原始料号：{result['原始料号']}")
    print()
    
    print("【解析结果】")
    for key, value in result['解析结果'].items():
        print(f"  {key:15s}: {value}")
    
    print()
    print("="*80)
    print("【标准格式输出】")
    print("="*80)
    print(result['标准格式'])
    print("="*80)


if __name__ == '__main__':
    main()

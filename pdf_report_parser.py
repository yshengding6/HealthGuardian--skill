"""
HealthGuardian - PDF 体检报告解析模块
使用 PyMuPDF 提取 PDF 文本，结构化解析异常项并写入数据库
"""

import fitz  # PyMuPDF
import re
import os
import json
from typing import List, Dict, Optional
from db_manager import DatabaseManager, MedicalRecord


class PDFReportParser:
    """PDF 体检报告解析器"""

    def __init__(self, db: DatabaseManager, reports_dir: str = "reports"):
        self.db = db
        self.reports_dir = reports_dir

    def extract_text(self, pdf_path: str) -> str:
        """提取 PDF 全文"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"文件不存在: {pdf_path}")

        doc = fitz.open(pdf_path)
        text_parts = []
        for page_num, page in enumerate(doc):
            page_text = page.get_text()
            if page_text.strip():
                text_parts.append(f"--- 第 {page_num + 1} 页 ---\n{page_text}")
        doc.close()

        full_text = "\n".join(text_parts)
        return full_text

    def parse_and_store(self, pdf_path: str, report_date: str,
                        report_type: str = "年度体检",
                        source_text: str = None) -> int:
        """
        解析 PDF 体检报告并将异常项存入数据库

        Args:
            pdf_path: PDF 文件路径
            report_date: 报告日期 YYYY-MM-DD
            report_type: 报告类型
            source_text: 可选，已有的提取文本（避免重复提取）

        Returns:
            写入的异常项数量
        """
        # 提取文本
        text = source_text or self.extract_text(pdf_path)

        # 将文本保存到 reports 目录供参考
        text_filename = os.path.splitext(os.path.basename(pdf_path))[0] + "_提取文本.txt"
        text_path = os.path.join(self.reports_dir, text_filename)
        if not source_text:  # 只在首次提取时保存
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(text)

        # 根据报告类型选择解析策略
        if "基因" in report_type:
            return self._parse_genetic_report(text, report_date)
        else:
            return self._parse_exam_report(text, report_date, report_type)

    def _parse_exam_report(self, text: str, report_date: str,
                           report_type: str) -> int:
        """
        解析常规体检报告，提取异常项

        策略：基于关键词模式匹配异常项
        """
        records = []

        # 分行处理
        lines = text.split('\n')
        current_section = ""

        # 异常标记模式
        abnormal_markers = [
            r'↑', r'↓', r'偏高', r'偏低', r'阳性', r'异常',
            r'增高', r'增高\(', r'降低', r'减少', r'增多',
            r'阳性\(', r'阴影', r'结节', r'钙化', r'囊肿',
            r'梗塞', r'梗死', r'缺血', r'炎症', r'退行性变',
            r'结石', r'脂肪肝', r'息肉', r'肿物', r'积液'
        ]

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 检查是否包含异常标记
            is_abnormal = any(re.search(pattern, line) for pattern in abnormal_markers)

            if is_abnormal and len(line) > 3:
                # 尝试提取结构化信息
                record = self._extract_record_from_line(line, report_date, report_type)
                if record:
                    records.append(record)

        # 去重并写入数据库
        seen = set()
        count = 0
        for record in records:
            key = (record.item_name, record.report_date)
            if key not in seen:
                seen.add(key)
                record_id = self.db.add_medical_record(record)
                if record_id:
                    count += 1

        return count

    def _parse_genetic_report(self, text: str, report_date: str) -> int:
        """解析基因检测报告，提取关键结果"""
        records = []
        lines = text.split('\n')

        # 基因检测关注的关键模式
        patterns = [
            (r'GJB2.*?携带者', 'GJB2基因突变-耳聋携带者'),
            (r'ALDH2.*?AG型|乙醛代谢慢', '乙醛代谢慢（ALDH2 AG型）'),
            (r'MTHFR.*?AA型|叶酸.*?低', '叶酸利用能力低（MTHFR AA型）'),
            (r'ADH1B.*?CC', '乙醇代谢慢（ADH1B CC）'),
            (r'硝酸甘油.*?代谢差|ALDH2.*?GA型', '硝酸甘油代谢差'),
            (r'CYP2C8.*?TT型', '罗格列酮代谢异常'),
            (r'UGT2B15.*?AA型', '劳拉西泮/奥沙西泮代谢慢'),
            (r'ABCB1.*?GG型', '奈韦拉平不良反应风险'),
            (r'NAT2.*?慢代谢', '异烟肼代谢慢'),
            (r'CYP2D6.*?代谢差', '他莫昔芬疗效欠佳'),
        ]

        text_block = '\n'.join(lines)
        matched_items = set()

        for pattern, item_name in patterns:
            if re.search(pattern, text_block) and item_name not in matched_items:
                matched_items.add(item_name)
                # 提取匹配行的上下文作为 detail
                for line in lines:
                    if re.search(pattern, line):
                        detail = line.strip()[:200]
                        records.append(MedicalRecord(
                            id=None,
                            report_date=report_date,
                            report_type="基因检测",
                            item_name=item_name,
                            value="见报告详情",
                            unit=None,
                            reference_range=None,
                            status="风险",
                            severity="需关注",
                            notes=detail
                        ))
                        break

        count = 0
        for record in records:
            record_id = self.db.add_medical_record(record)
            if record_id:
                count += 1

        return count

    def _extract_record_from_line(self, line: str, report_date: str,
                                   report_type: str) -> Optional[MedicalRecord]:
        """从单行文本中提取结构化异常项记录"""
        # 尝试提取数值模式: 项目名 + 数值 + 单位 + (参考范围) + 状态
        patterns = [
            # 总胆固醇 4.54 mmol/L ↑ 参考: <5.2
            r'(.+?)\s*([\d.]+)\s*(mmol/L|g/L|U/L|μg/L|pg/mL|nmol/L|%/L|%|fl|pg|×10⁹/L|×10¹²/L|dpm|mg/L|mg/dL)?\s*([↑↓]?)\s*(?:参考[：:范围值]?\s*([^)\n]+))?',
        ]

        severity_map = {
            '危险': '严重', '高': '中度', '中': '中度',
            '轻': '轻微', '低': '无', '正常': '无'
        }

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                item_name = match.group(1).strip()
                value = match.group(2).strip()
                unit = match.group(3) if match.group(3) else ''
                arrow = match.group(4) if match.group(4) else ''
                ref_range = match.group(5).strip() if match.group(5) else ''

                # 过滤掉太短或不太合理的匹配
                if len(item_name) < 2 or len(item_name) > 50:
                    continue
                if item_name.startswith('-') or item_name.startswith('='):
                    continue

                # 判断状态
                if '↑' in arrow or '偏高' in line or '增高' in line or '增多' in line:
                    status = '偏高↑'
                elif '↓' in arrow or '偏低' in line or '降低' in line or '减少' in line:
                    status = '偏低↓'
                elif '阳性' in line:
                    status = '阳性'
                else:
                    status = '异常'

                # 判断严重程度
                severity = '轻微'
                for key, val in severity_map.items():
                    if key in line:
                        severity = val
                        break

                return MedicalRecord(
                    id=None,
                    report_date=report_date,
                    report_type=report_type,
                    item_name=item_name,
                    value=value,
                    unit=unit or None,
                    reference_range=ref_range or None,
                    status=status,
                    severity=severity,
                    notes=line.strip()[:200]
                )

        # 如果数值模式没匹配到，但有明确异常关键词，也记录
        abnormal_keywords = ['结节', '囊肿', '钙化', '结石', '梗塞', '梗死',
                           '缺血', '炎症', '退行性变', '脂肪肝', '息肉',
                           '肿物', '积液', '阴影', '闭塞', '狭窄']
        for kw in abnormal_keywords:
            if kw in line:
                # 尝试提取项目名（关键词前面的部分）
                parts = line.split(kw)
                item_name = parts[0].strip().split('\n')[-1].strip()
                if not item_name or len(item_name) < 2:
                    item_name = line.strip()[:40]

                return MedicalRecord(
                    id=None,
                    report_date=report_date,
                    report_type=report_type,
                    item_name=item_name + kw if len(item_name) < 20 else item_name,
                    value="见报告详情",
                    unit=None,
                    reference_range=None,
                    status='异常',
                    severity='需关注',
                    notes=line.strip()[:200]
                )

        return None

    def batch_parse_reports(self) -> Dict[str, int]:
        """
        批量解析 reports 目录下所有 PDF 文件

        Returns:
            {文件名: 写入记录数}
        """
        results = {}
        if not os.path.exists(self.reports_dir):
            return results

        # 报告日期映射（根据文件名推断）
        date_mapping = {
            "2025": "2025-07-01",
            "202302": "2023-02-24",
            "基因": "2024-05-31",
        }
        type_mapping = {
            "2025": "年度体检",
            "202302": "年度体检",
            "基因": "基因检测",
        }

        for filename in os.listdir(self.reports_dir):
            if not filename.lower().endswith('.pdf'):
                continue

            report_date = None
            report_type = "年度体检"
            for key, date in date_mapping.items():
                if key in filename:
                    report_date = date
                    report_type = type_mapping[key]
                    break

            if not report_date:
                continue  # 未知报告，跳过

            pdf_path = os.path.join(self.reports_dir, filename)
            try:
                count = self.parse_and_store(pdf_path, report_date, report_type)
                results[filename] = count
            except Exception as e:
                results[filename] = f"错误: {e}"

        return results

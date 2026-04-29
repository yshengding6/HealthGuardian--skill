"""
HealthGuardian-Skill - 体检报告解析模块
提供图片预处理与 Claude Vision API 整合
"""

import os
import json
import base64
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from PIL import Image, ImageEnhance, ImageFilter
import io


@dataclass
class ReportParseResult:
    """体检报告解析结果数据类"""
    report_date: str
    report_type: str
    patient_info: Dict[str, str]
    test_items: List[Dict[str, Any]]
    summary: Dict[str, Any]
    raw_text: str
    parse_status: str  # success/partial/failed
    confidence: float  # 解析置信度 0-1


class ImagePreprocessor:
    """图片预处理类"""

    # 支持的图片格式
    SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.webp'}

    # 最大图片尺寸（像素）
    MAX_WIDTH = 3000
    MAX_HEIGHT = 3000

    # 最小图片尺寸（像素）
    MIN_WIDTH = 800
    MIN_HEIGHT = 600

    def __init__(self):
        """初始化图片预处理器"""
        self.temp_dir = Path("temp_images")
        self.temp_dir.mkdir(exist_ok=True)

    def validate_image(self, image_path: str) -> tuple[bool, str]:
        """
        验证图片文件

        Args:
            image_path: 图片文件路径

        Returns:
            (是否有效, 错误信息)
        """
        path = Path(image_path)

        if not path.exists():
            return False, "图片文件不存在"

        if path.suffix.lower() not in self.SUPPORTED_FORMATS:
            return False, f"不支持的图片格式：{path.suffix}，支持的格式：{self.SUPPORTED_FORMATS}"

        # 检查文件大小（限制 10MB）
        file_size = path.stat().st_size
        if file_size > 10 * 1024 * 1024:
            return False, f"图片文件过大：{file_size / (1024 * 1024):.1f} MB（限制 10 MB）"

        try:
            with Image.open(image_path) as img:
                width, height = img.size

                if width < self.MIN_WIDTH or height < self.MIN_HEIGHT:
                    return False, f"图片分辨率过低：{width}x{height}（建议至少 {self.MIN_WIDTH}x{self.MIN_HEIGHT}）"

                return True, "验证通过"

        except Exception as e:
            return False, f"无法打开图片：{str(e)}"

    def preprocess_image(self, image_path: str, enhance: bool = True) -> tuple[str, str]:
        """
        预处理图片以提升 OCR 识别准确度

        Args:
            image_path: 原始图片路径
            enhance: 是否增强图片品质

        Returns:
            (预处理后的图片路径, 处理日志)
        """
        path = Path(image_path)
        output_path = self.temp_dir / f"processed_{path.name}"

        log_messages = []

        try:
            with Image.open(image_path) as img:
                log_messages.append(f"原始尺寸: {img.size[0]}x{img.size[1]}")

                # 转换为 RGB（如果需要）
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                    log_messages.append("转换为 RGB 格式")

                # 调整尺寸（如果超过最大值）
                if img.size[0] > self.MAX_WIDTH or img.size[1] > self.MAX_HEIGHT:
                    img.thumbnail((self.MAX_WIDTH, self.MAX_HEIGHT), Image.LANCZOS)
                    log_messages.append(f"调整尺寸至: {img.size[0]}x{img.size[1]}")

                # 增强图片品质
                if enhance:
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(1.2)
                    log_messages.append("提升对比度 20%")

                    img = img.filter(ImageFilter.SHARPEN)
                    log_messages.append("应用锐化滤镜")

                img.save(output_path, 'JPEG', quality=95, optimize=True)
                log_messages.append(f"保存至: {output_path}")

                return str(output_path), "\n".join(log_messages)

        except Exception as e:
            raise RuntimeError(f"图片预处理失败：{str(e)}")

    def image_to_base64(self, image_path: str) -> str:
        """将图片转换为 Base64 编码"""
        with open(image_path, 'rb') as f:
            return base64.b64encode(f.read()).decode('utf-8')

    def get_image_info(self, image_path: str) -> Dict[str, Any]:
        """获取图片信息"""
        with Image.open(image_path) as img:
            return {
                "format": img.format,
                "mode": img.mode,
                "size": img.size,
                "width": img.width,
                "height": img.height,
                "file_size": Path(image_path).stat().st_size
            }

    def batch_preprocess(self, image_paths: List[str]) -> List[tuple[str, str, bool]]:
        """
        批量预处理多张图片

        Returns:
            [(输出路径, 日志, 是否成功), ...]
        """
        results = []
        for path in image_paths:
            try:
                valid, msg = self.validate_image(path)
                if not valid:
                    results.append((path, f"验证失败: {msg}", False))
                    continue

                output, log = self.preprocess_image(path)
                results.append((output, log, True))

            except Exception as e:
                results.append((path, f"处理失败: {str(e)}", False))

        return results


class MedReportAnalyzer:
    """体检报告分析器 - 整合 Claude Vision API"""

    def __init__(self, db_manager=None):
        """
        初始化体检报告分析器

        Args:
            db_manager: 数据库管理器实例
        """
        self.preprocessor = ImagePreprocessor()
        self.db_manager = db_manager

        self.prompt_template = self._load_prompt_template()

    def _load_prompt_template(self) -> str:
        """加载 OCR 提示词模板"""
        template_path = Path("prompts/ocr_template.txt")

        if not template_path.exists():
            return """
请仔细识别这张体检报告图片，提取所有检查项目的信息。
输出格式为 JSON，包含以下字段：
- report_date: 报告日期
- report_type: 报告类型
- patient_info: 患者信息（姓名、年龄、性别）
- test_items: 检查项目列表（包含检查项目、数值、单位、参考范围、状态、严重程度）
- summary: 摘要信息
- raw_text: 原始识别文字
"""

        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def analyze_report(self, image_path: str) -> ReportParseResult:
        """
        分析体检报告图片

        Args:
            image_path: 体检报告图片路径

        Returns:
            解析结果
        """
        valid, msg = self.preprocessor.validate_image(image_path)
        if not valid:
            return ReportParseResult(
                report_date="",
                report_type="",
                patient_info={},
                test_items=[],
                summary={},
                raw_text=msg,
                parse_status="failed",
                confidence=0.0
            )

        processed_path, process_log = self.preprocessor.preprocess_image(image_path)
        image_info = self.preprocessor.get_image_info(processed_path)
        base64_image = self.preprocessor.image_to_base64(processed_path)

        return {
            "status": "ready_for_analysis",
            "processed_image": processed_path,
            "base64_image": base64_image,
            "image_info": image_info,
            "process_log": process_log,
            "prompt": self.prompt_template
        }

    def save_to_database(self, parsed_data: Dict[str, Any]) -> int:
        """
        将解析结果保存到数据库

        Returns:
            保存的记录数
        """
        from db_manager import MedicalRecord

        if not self.db_manager:
            raise RuntimeError("数据库管理器未初始化")

        saved_count = 0

        for item in parsed_data.get('test_items', []):
            if item.get('status') not in ['正常', '']:
                record = MedicalRecord(
                    id=None,
                    report_date=parsed_data.get('report_date', datetime.now().strftime('%Y-%m-%d')),
                    report_type=parsed_data.get('report_type', '体检报告'),
                    item_name=item.get('item_name', ''),
                    value=item.get('value', ''),
                    unit=item.get('unit'),
                    reference_range=item.get('reference_range'),
                    status=item.get('status', ''),
                    severity=item.get('severity', '无'),
                    notes=item.get('notes')
                )
                self.db_manager.add_medical_record(record)
                saved_count += 1

        return saved_count

    def generate_summary_report(self, report_date: str) -> Dict[str, Any]:
        """
        生成体检报告摘要

        Returns:
            摘要报告
        """
        if not self.db_manager:
            raise RuntimeError("数据库管理器未初始化")

        records = self.db_manager.get_medical_records(report_date)

        summary = {
            "report_date": report_date,
            "total_items": len(records),
            "abnormal_items": [r for r in records if r.status != '正常'],
            "by_severity": {
                "轻微": len([r for r in records if r.severity == '轻微']),
                "中度": len([r for r in records if r.severity == '中度']),
                "严重": len([r for r in records if r.severity == '严重'])
            },
            "recommendations": self._generate_recommendations(records)
        }

        return summary

    def _generate_recommendations(self, records: List) -> List[str]:
        """根据异常项目生成建议"""
        recommendations = []

        for record in records:
            item_name = record.item_name.lower()

            if '胆固醇' in item_name or '血脂' in item_name:
                recommendations.append("建议控制饮食，减少动物性脂肪摄入，适量运动")

            elif '血糖' in item_name:
                if record.severity == '严重':
                    recommendations.append("血糖异常严重，建议尽快就医检查")

            elif '血压' in item_name:
                if record.severity in ['中度', '严重']:
                    recommendations.append("血压偏高，建议监测并咨询医生意见")

        if not recommendations:
            recommendations.append("整体指标良好，请保持健康的生活方式")

        return recommendations

    def cleanup_temp_files(self):
        """清理临时文件"""
        if self.preprocessor.temp_dir.exists():
            for file in self.preprocessor.temp_dir.glob('processed_*'):
                try:
                    file.unlink()
                except Exception:
                    pass


# ========== 测试代码 ==========
if __name__ == "__main__":
    print("体检报告分析器测试")
    print("-" * 50)

    analyzer = MedReportAnalyzer()

    print(f"支持的图片格式: {ImagePreprocessor.SUPPORTED_FORMATS}")
    print(f"最大图片尺寸: {ImagePreprocessor.MAX_WIDTH}x{ImagePreprocessor.MAX_HEIGHT}")
    print(f"最小图片尺寸: {ImagePreprocessor.MIN_WIDTH}x{ImagePreprocessor.MIN_HEIGHT}")
    print("-" * 50)

    test_image = "sample_report.jpg"
    if Path(test_image).exists():
        valid, msg = analyzer.preprocessor.validate_image(test_image)
        print(f"图片验证: {valid} - {msg}")

        if valid:
            result = analyzer.analyze_report(test_image)
            print(f"分析状态: {result['status']}")
            print(f"处理后图片: {result['processed_image']}")
    else:
        print(f"测试图片 {test_image} 不存在")

    print("-" * 50)
    print("测试完成！")

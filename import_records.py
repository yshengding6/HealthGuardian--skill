"""
一次性脚本示例：将体检报告异常项写入 medical_records 表

使用方法：
1. 根据自己的体检报告修改下方 records 列表
2. 运行: python import_records.py
3. 首次运行会自动创建数据库和表结构
"""
import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_manager import DatabaseManager, MedicalRecord


def import_records():
    with DatabaseManager('health_log.db') as db:
        # 示例记录（请替换为自己的体检数据）
        records = [
            MedicalRecord(
                id=None, report_date='2025-07-01', report_type='年度体检',
                item_name='示例异常项', value='偏高', unit='mmol/L',
                reference_range='<5.2', status='偏高↑', severity='轻微',
                notes='示例备注'
            ),
            # 在此添加更多记录...
        ]

        count = 0
        for record in records:
            db.add_medical_record(record)
            count += 1
            print(f"  写入: {record.item_name}")

        print(f'\n共写入 {count} 条记录')


if __name__ == '__main__':
    import_records()

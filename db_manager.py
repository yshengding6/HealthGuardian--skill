"""
HealthGuardian - 数据库管理模块 v3
提供 SQLite 数据库的初始化与基本操作接口
支持：每日指标、体检记录、药品管理、生活习惯、病史、健康日记、就医计划、服药日志
新增：版本化迁移、多记忆架构、健康洞察引擎、服药闭环管理、用药清单制、完整性检查
Schema: v6 (medication_logs.schedule_slot, medications.med_type/schedule_time/end_date)
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, field
import json
import os
import re

# ============================================================
# Schema 版本管理
# ============================================================
SCHEMA_VERSION = 6


# ============================================================
# 数据类定义
# ============================================================

@dataclass
class DailyMetric:
    """每日健康指标数据类"""
    id: Optional[int]
    date: str
    systolic_bp: Optional[int] = None       # 收缩压 (mmHg)
    diastolic_bp: Optional[int] = None      # 舒张压 (mmHg)
    heart_rate: Optional[int] = None        # 心率 (bpm)
    fasting_glucose: Optional[float] = None # 空腹血糖 (mmol/L)
    sleep_hours: Optional[float] = None     # 睡眠时长
    sleep_quality: Optional[int] = None     # 睡眠质量 (1-5)
    steps: Optional[int] = None             # 步数
    notes: Optional[str] = None             # 备注


@dataclass
class MedicalRecord:
    """体检报告异常项数据类"""
    id: Optional[int]
    report_date: str
    report_type: str                # 报告类型（体检/化验/影像等）
    item_name: str                  # 检查项目名称
    value: str                      # 数值（保留原始字符串）
    unit: Optional[str] = None      # 单位
    reference_range: Optional[str] = None  # 参考范围
    status: str = ''                # 状态（正常/偏高/偏低）
    severity: str = ''              # 严重程度（无/轻微/中度/严重）
    notes: Optional[str] = None     # 备注


@dataclass
class Medication:
    """药品管理数据类"""
    id: Optional[int]
    name: str                       # 药品名称
    dosage: str                     # 剂量规格
    frequency: str                  # 服用频率
    total_quantity: int             # 总数量
    remaining_quantity: int         # 剩余数量
    expiry_date: str                # 有效期
    start_date: str                 # 开始服用日期
    dose_quantity: float = 1.0      # 每次服用片数（默认1片）
    notes: Optional[str] = None     # 备注
    med_type: str = '长期'          # 药物类型：长期/阶段性/临时处方
    schedule_time: str = '早'       # 服药时段：早/中/晚/睡前，多选用逗号分隔
    end_date: Optional[str] = None  # 疗程结束日期（阶段性/临时处方用）


@dataclass
class MedicationLog:
    """服药记录数据类（每次实际服药）"""
    id: Optional[int]
    medication_id: int              # 关联药品 ID
    date: str                       # 服药日期 YYYY-MM-DD
    time: Optional[str] = None      # 服药时间 HH:MM
    dosage_taken: str = ''          # 实际服用的剂量
    is_on_time: Optional[int] = 1   # 是否按时（1=是, 0=否）
    notes: Optional[str] = None     # 备注
    schedule_slot: Optional[str] = None  # 服药时段：早/中/晚/睡前


@dataclass
class HealthLog:
    """健康日记/症状日志数据类（与 daily_metrics 纯数值分离）"""
    id: Optional[int]
    date: str                       # 日期 YYYY-MM-DD
    category: str                   # 分类：症状/就诊/用药/其他
    title: str                      # 简短标题
    content: str                    # 详细内容
    severity: Optional[str] = None  # 严重程度：轻/中/重
    updated_at: Optional[str] = None


@dataclass
class FollowUpAction:
    """就医待办/复查计划数据类"""
    id: Optional[int]
    title: str                      # 待办标题
    category: str                   # 分类：复查/就诊/检验/其他
    due_date: Optional[str] = None  # 截止日期 YYYY-MM-DD
    priority: str = '中'            # 优先级：高/中/低
    status: str = '待办'            # 状态：待办/进行中/已完成/已取消
    source: Optional[str] = None    # 来源（哪份报告/哪次对话）
    notes: Optional[str] = None     # 备注
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class AlertResult:
    """预警检查结果"""
    item: str                       # 指标名称
    value: float                    # 实际值
    level: str                      # 预警级别
    message: str                    # 预警信息


@dataclass
class HealthInsight:
    """健康洞察结果"""
    category: str                   # 洞察类别：药效/症状关联/体检趋势/生活习惯
    title: str                      # 洞察标题
    detail: str                     # 详细说明
    confidence: float               # 置信度 0-1
    data_points: int                # 基于多少条数据


# ============================================================
# 频率解析工具
# ============================================================

def parse_frequency(frequency: str) -> float:
    """
    解析服药频率为每日用量

    Examples:
        "每日1次" → 1.0
        "每日2次" → 2.0
        "每周3次" → 0.43
        "每日1次(早)" → 1.0
    """
    frequency = frequency.strip()
    m = re.match(r'每[日天](\d+)次', frequency)
    if m:
        return float(m.group(1))
    m = re.match(r'每[周日](\d+)次', frequency)
    if m:
        return float(m.group(1)) / 7.0
    m = re.match(r'(\d+)[日天](\d+)次', frequency)
    if m:
        return float(m.group(2)) / float(m.group(1))
    # 默认按每日1次
    return 1.0


# ============================================================
# 数据库管理核心
# ============================================================

class DatabaseManager:
    """HealthGuardian 数据库管理类 v3"""

    def __init__(self, db_path: str = "health_log.db"):
        """
        初始化数据库管理器，自动执行 schema 迁移

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self.conn = None
        self._initialize_database()
        self._migrate_database()

    def _get_connection(self) -> sqlite3.Connection:
        """获取数据库连接"""
        if self.conn is None:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
        return self.conn

    def _initialize_database(self) -> None:
        """初始化数据库基础表结构（仅 CREATE IF NOT EXISTS）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # schema 版本元数据表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _meta (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # 1. 每日健康指标表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                heart_rate INTEGER,
                fasting_glucose REAL,
                sleep_hours REAL,
                sleep_quality INTEGER CHECK(sleep_quality BETWEEN 1 AND 5),
                steps INTEGER,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. 体检报告异常项表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medical_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT NOT NULL,
                report_type TEXT NOT NULL,
                item_name TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT,
                reference_range TEXT,
                status TEXT NOT NULL,
                severity TEXT NOT NULL,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 3. 药品管理表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                dosage TEXT NOT NULL,
                frequency TEXT NOT NULL,
                total_quantity INTEGER NOT NULL,
                remaining_quantity INTEGER NOT NULL,
                expiry_date TEXT NOT NULL,
                start_date TEXT NOT NULL,
                notes TEXT,
                is_active INTEGER DEFAULT 1,
                low_stock_threshold INTEGER DEFAULT 7,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. 生活习惯表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS lifestyle (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                sub_category TEXT,
                content TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
            )
        """)

        # 5. 病史表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS medical_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                year TEXT NOT NULL,
                disease TEXT NOT NULL,
                detail TEXT,
                treatment TEXT,
                outcome TEXT,
                updated_at TIMESTAMP DEFAULT (datetime('now','localtime'))
            )
        """)

        # 6. 健康日记/症状日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS health_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                severity TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 7. 就医待办/复查计划表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS follow_up_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                category TEXT NOT NULL,
                due_date TEXT,
                priority TEXT NOT NULL DEFAULT '中',
                status TEXT NOT NULL DEFAULT '待办',
                source TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medical_records_date ON medical_records(report_date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_medications_expiry ON medications(expiry_date)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_health_logs_date ON health_logs(date DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_follow_up_status ON follow_up_actions(status, due_date)")

        conn.commit()

    # ========== Schema 迁移 ==========

    def _get_schema_version(self) -> int:
        """获取当前数据库的 schema 版本号"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM _meta WHERE key = 'schema_version'")
        row = cursor.fetchone()
        if row:
            return int(row['value'])
        return 1  # 初始版本（迁移机制引入前的版本）

    def _set_schema_version(self, version: int) -> None:
        """设置 schema 版本号"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO _meta (key, value) VALUES ('schema_version', ?)
        """, (str(version),))
        conn.commit()

    def _migrate_database(self) -> None:
        """自动迁移数据库到最新 schema 版本"""
        current = self._get_schema_version()
        conn = self._get_connection()
        cursor = conn.cursor()

        if current < 2:
            # v1→v2: 确保 medications 表有 low_stock_threshold 列
            cursor.execute("PRAGMA table_info(medications)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'low_stock_threshold' not in columns:
                cursor.execute(
                    "ALTER TABLE medications ADD COLUMN low_stock_threshold INTEGER DEFAULT 7"
                )
            conn.commit()
            print(f"  数据库迁移: v1 -> v2 (medications.low_stock_threshold)")

        if current < 3:
            # v2→v3: 新增 medication_logs 表（服药记录）
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS medication_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medication_id INTEGER NOT NULL,
                    date TEXT NOT NULL,
                    time TEXT,
                    dosage_taken TEXT NOT NULL DEFAULT '',
                    is_on_time INTEGER DEFAULT 1,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (medication_id) REFERENCES medications(id)
                )
            """)
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_medication_logs_date "
                "ON medication_logs(date DESC, medication_id)"
            )
            conn.commit()
            print(f"  数据库迁移: v2 -> v3 (medication_logs 表)")

        if current < 4:
            # v3→v4: medications 表增加 dose_quantity 列（每次服用片数）
            cursor.execute("PRAGMA table_info(medications)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'dose_quantity' not in columns:
                cursor.execute(
                    "ALTER TABLE medications ADD COLUMN dose_quantity REAL DEFAULT 1.0"
                )
            conn.commit()
            print(f"  数据库迁移: v3 -> v4 (medications.dose_quantity)")

        if current < 5:
            # v4→v5: medications 表增加 med_type/schedule_time/end_date 列
            cursor.execute("PRAGMA table_info(medications)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'med_type' not in columns:
                cursor.execute(
                    "ALTER TABLE medications ADD COLUMN med_type TEXT DEFAULT '长期'"
                )
            if 'schedule_time' not in columns:
                cursor.execute(
                    "ALTER TABLE medications ADD COLUMN schedule_time TEXT DEFAULT '早'"
                )
            if 'end_date' not in columns:
                cursor.execute(
                    "ALTER TABLE medications ADD COLUMN end_date TEXT"
                )
            conn.commit()
            print(f"  数据库迁移: v4 -> v5 (medications.med_type/schedule_time/end_date)")

        if current < 6:
            # v5→v6: medication_logs 表增加 schedule_slot 列（服药时段）
            cursor.execute("PRAGMA table_info(medication_logs)")
            columns = [row['name'] for row in cursor.fetchall()]
            if 'schedule_slot' not in columns:
                cursor.execute(
                    "ALTER TABLE medication_logs ADD COLUMN schedule_slot TEXT"
                )
            conn.commit()
            print(f"  数据库迁移: v5 -> v6 (medication_logs.schedule_slot)")

        if current < SCHEMA_VERSION:
            self._set_schema_version(SCHEMA_VERSION)
            print(f"  数据库迁移完成，当前版本: v{SCHEMA_VERSION}")

    def get_schema_version(self) -> int:
        """公开方法：获取当前 schema 版本"""
        return self._get_schema_version()

    # ========== 每日健康指标操作 ==========

    def add_daily_metric(self, metric: DailyMetric) -> int:
        """新增每日健康指标（同一天只更新非 NULL 字段，保留已有数据）"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # 先检查当天是否已有记录
        cursor.execute("SELECT id FROM daily_metrics WHERE date = ?", (metric.date,))
        existing = cursor.fetchone()

        if existing:
            # 逐字段更新：只覆盖非 NULL 的新值，保留已有数据
            updates = []
            values = []
            field_map = {
                'systolic_bp': metric.systolic_bp,
                'diastolic_bp': metric.diastolic_bp,
                'heart_rate': metric.heart_rate,
                'fasting_glucose': metric.fasting_glucose,
                'sleep_hours': metric.sleep_hours,
                'sleep_quality': metric.sleep_quality,
                'steps': metric.steps,
                'notes': metric.notes,
            }
            for field, value in field_map.items():
                if value is not None:
                    updates.append(f"{field} = ?")
                    values.append(value)
            if updates:
                updates.append("updated_at = CURRENT_TIMESTAMP")
                values.append(metric.date)
                cursor.execute(
                    f"UPDATE daily_metrics SET {', '.join(updates)} WHERE date = ?",
                    values
                )
            conn.commit()
            return existing['id']
        else:
            cursor.execute("""
                INSERT INTO daily_metrics
                (date, systolic_bp, diastolic_bp, heart_rate, fasting_glucose,
                 sleep_hours, sleep_quality, steps, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.date, metric.systolic_bp, metric.diastolic_bp,
                metric.heart_rate, metric.fasting_glucose,
                metric.sleep_hours, metric.sleep_quality, metric.steps, metric.notes
            ))
            conn.commit()
            return cursor.lastrowid

    def get_daily_metric(self, date: str) -> Optional[DailyMetric]:
        """取得指定日期的健康指标"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_metrics WHERE date = ?", (date,))
        row = cursor.fetchone()
        if row:
            return self._row_to_metric(row)
        return None

    def get_recent_metrics(self, days: int = 30) -> List[DailyMetric]:
        """取得最近 N 天的健康指标"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM daily_metrics
            WHERE date >= date('now', ?)
            ORDER BY date DESC
        """, (f'-{days} days',))
        return [self._row_to_metric(row) for row in cursor.fetchall()]

    def get_metric_stats(self, days: int = 30) -> Dict[str, Dict[str, Any]]:
        """
        获取最近 N 天的指标统计摘要

        Returns:
            {
                "systolic_bp": {"avg": 128, "min": 115, "max": 142, "count": 15, "trend": "上升"},
                "fasting_glucose": {"avg": 5.6, "min": 5.2, "max": 6.1, "count": 10, "trend": "稳定"},
                ...
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        fields = {
            'systolic_bp': '收缩压',
            'diastolic_bp': '舒张压',
            'heart_rate': '心率',
            'fasting_glucose': '空腹血糖',
            'sleep_hours': '睡眠时长',
            'steps': '步数',
        }
        stats = {}
        for col, label in fields.items():
            cursor.execute(f"""
                SELECT AVG({col}) as avg, MIN({col}) as min, MAX({col}) as max, COUNT({col}) as cnt
                FROM daily_metrics
                WHERE date >= date('now', ?) AND {col} IS NOT NULL
            """, (f'-{days} days',))
            row = cursor.fetchone()
            if row and row['cnt'] > 0:
                avg_val = row['avg']
                stats[col] = {
                    'label': label,
                    'avg': round(avg_val, 1) if isinstance(avg_val, float) else avg_val,
                    'min': row['min'],
                    'max': row['max'],
                    'count': row['cnt'],
                }
        return stats

    def _row_to_metric(self, row: sqlite3.Row) -> DailyMetric:
        """将数据库行转换为 DailyMetric 对象"""
        return DailyMetric(
            id=row['id'], date=row['date'],
            systolic_bp=row['systolic_bp'], diastolic_bp=row['diastolic_bp'],
            heart_rate=row['heart_rate'], fasting_glucose=row['fasting_glucose'],
            sleep_hours=row['sleep_hours'], sleep_quality=row['sleep_quality'],
            steps=row['steps'], notes=row['notes']
        )

    # ========== 体检报告操作 ==========

    def add_medical_record(self, record: MedicalRecord) -> int:
        """新增体检报告异常项"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO medical_records
            (report_date, report_type, item_name, value, unit,
             reference_range, status, severity, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record.report_date, record.report_type, record.item_name,
            record.value, record.unit, record.reference_range,
            record.status, record.severity, record.notes
        ))
        conn.commit()
        return cursor.lastrowid

    def get_medical_records(self, report_date: Optional[str] = None) -> List[MedicalRecord]:
        """取得体检报告记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if report_date:
            cursor.execute(
                "SELECT * FROM medical_records WHERE report_date = ? ORDER BY id",
                (report_date,)
            )
        else:
            cursor.execute("SELECT * FROM medical_records ORDER BY report_date DESC, id")
        return [self._row_to_medical_record(row) for row in cursor.fetchall()]

    def get_medical_record_trends(self) -> List[Dict]:
        """
        获取跨年体检指标变化趋势

        Returns:
            [{"item_name": "总胆固醇", "values": [{"date": "2023", "value": "5.8"}, ...]}]
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT item_name, report_date, value, status, unit
            FROM medical_records
            ORDER BY item_name, report_date ASC
        """)
        records = cursor.fetchall()

        trends = {}
        for row in records:
            name = row['item_name']
            if name not in trends:
                trends[name] = []
            trends[name].append({
                'date': row['report_date'],
                'value': row['value'],
                'status': row['status'],
                'unit': row['unit'],
            })
        return [{'item_name': k, 'values': v} for k, v in trends.items() if len(v) > 1]

    def _row_to_medical_record(self, row: sqlite3.Row) -> MedicalRecord:
        """将数据库行转换为 MedicalRecord 对象"""
        return MedicalRecord(
            id=row['id'], report_date=row['report_date'],
            report_type=row['report_type'], item_name=row['item_name'],
            value=row['value'], unit=row['unit'],
            reference_range=row['reference_range'],
            status=row['status'], severity=row['severity'], notes=row['notes']
        )

    # ========== 药品管理操作 ==========

    def add_medication(self, medication: Medication) -> int:
        """新增药品记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO medications
            (name, dosage, frequency, total_quantity, remaining_quantity,
             expiry_date, start_date, dose_quantity, notes,
             med_type, schedule_time, end_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            medication.name, medication.dosage, medication.frequency,
            medication.total_quantity, medication.remaining_quantity,
            medication.expiry_date, medication.start_date,
            medication.dose_quantity, medication.notes,
            medication.med_type, medication.schedule_time, medication.end_date
        ))
        conn.commit()
        return cursor.lastrowid

    def update_medication_quantity(self, med_id: int, used_quantity: int) -> bool:
        """更新药品剩余数量"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE medications
            SET remaining_quantity = remaining_quantity - ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND remaining_quantity >= ?
        """, (used_quantity, med_id, used_quantity))
        conn.commit()
        return cursor.rowcount > 0

    def get_medications(self, active_only: bool = True) -> List[Dict]:
        """取得药品列表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if active_only:
            cursor.execute("""
                SELECT * FROM medications
                WHERE is_active = 1 AND remaining_quantity > 0
                ORDER BY expiry_date ASC
            """)
        else:
            cursor.execute("""
                SELECT * FROM medications
                ORDER BY is_active DESC, expiry_date ASC
            """)
        return [dict(row) for row in cursor.fetchall()]

    # ========== 服药日志 ==========

    def log_medication(self, med_log: MedicationLog) -> int:
        """
        记录一次服药

        同时自动扣减药品库存（根据 dose_quantity 动态扣减）
        验证 medication_id 存在，不存在则抛出 ValueError
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 验证药品存在
        cursor.execute(
            "SELECT id, dose_quantity FROM medications WHERE id = ?",
            (med_log.medication_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise ValueError(f"药品 ID {med_log.medication_id} 不存在，无法记录服药")
        dose_qty = row['dose_quantity'] or 1.0

        # 插入服药记录（含 schedule_slot）
        cursor.execute("""
            INSERT INTO medication_logs
            (medication_id, date, time, dosage_taken, is_on_time, notes, schedule_slot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            med_log.medication_id, med_log.date, med_log.time,
            med_log.dosage_taken, med_log.is_on_time, med_log.notes,
            med_log.schedule_slot
        ))
        log_id = cursor.lastrowid

        # 自动扣减库存（按实际每次服用片数）
        cursor.execute("""
            UPDATE medications
            SET remaining_quantity = MAX(0, remaining_quantity - ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_active = 1
        """, (dose_qty, med_log.medication_id))

        # 库存归零自动标记
        cursor.execute("""
            UPDATE medications
            SET is_active = 0, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND remaining_quantity = 0
        """, (med_log.medication_id,))

        conn.commit()
        return log_id

    def get_medication_logs(self, medication_id: Optional[int] = None,
                            days: int = 30) -> List[Dict]:
        """查询服药记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if medication_id:
            cursor.execute("""
                SELECT ml.*, m.name as medication_name
                FROM medication_logs ml
                JOIN medications m ON ml.medication_id = m.id
                WHERE ml.medication_id = ? AND ml.date >= date('now', ?)
                ORDER BY ml.date DESC, ml.time DESC
            """, (medication_id, f'-{days} days'))
        else:
            cursor.execute("""
                SELECT ml.*, m.name as medication_name
                FROM medication_logs ml
                JOIN medications m ON ml.medication_id = m.id
                WHERE ml.date >= date('now', ?)
                ORDER BY ml.date DESC, ml.time DESC
            """, (f'-{days} days',))
        return [dict(row) for row in cursor.fetchall()]

    def get_adherence_rate(self, medication_id: int, days: int = 30) -> Dict:
        """
        计算用药依从性

        Returns:
            {
                "medication_name": "示例降压药",
                "period_days": 30,
                "expected_doses": 30,
                "actual_doses": 25,
                "on_time_doses": 22,
                "adherence_rate": 83.3,
                "on_time_rate": 88.0,
                "missed_dates": ["2026-04-15", "2026-04-16"]
            }
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # 获取药品信息
        cursor.execute("SELECT * FROM medications WHERE id = ?", (medication_id,))
        med = cursor.fetchone()
        if not med:
            return {}

        daily_dose = parse_frequency(med['frequency'])

        # 统计实际服药次数
        cursor.execute("""
            SELECT date, COUNT(*) as doses, SUM(is_on_time) as on_time
            FROM medication_logs
            WHERE medication_id = ? AND date >= date('now', ?)
            GROUP BY date
        """, (medication_id, f'-{days} days'))
        log_rows = cursor.fetchall()

        actual_dates = set()
        actual_doses = 0
        on_time_doses = 0
        for row in log_rows:
            actual_dates.add(row['date'])
            actual_doses += row['doses']
            on_time_doses += row['on_time'] or 0

        # 计算预期剂量：考虑 start_date 和 end_date
        start = datetime.strptime(med['start_date'], '%Y-%m-%d')
        now = datetime.now()
        lookback_start = now - timedelta(days=days)
        # 有效计算起始日 = max(lookback起点, start_date)
        effective_start = max(start, lookback_start)
        # 有效计算终止日 = min(今天, end_date 或 今天)
        end_date_str = med.get('end_date') if hasattr(med, 'get') else None
        # 从 dict 兼容取值
        try:
            end_date_str = med['end_date']
        except (KeyError, TypeError):
            end_date_str = None
        if end_date_str:
            effective_end = min(now, datetime.strptime(end_date_str, '%Y-%m-%d'))
        else:
            effective_end = now
        effective_days = max(1, (effective_end - effective_start).days + 1)
        expected = int(effective_days * daily_dose)

        rate = round(actual_doses / expected * 100, 1) if expected > 0 else 0
        on_time_rate = round(on_time_doses / actual_doses * 100, 1) if actual_doses > 0 else 0

        # 计算漏服日期（只在有效区间内）
        missed = []
        check = effective_start
        while check <= effective_end:
            if check.strftime('%Y-%m-%d') not in actual_dates:
                missed.append(check.strftime('%Y-%m-%d'))
            check += timedelta(days=1)

        return {
            'medication_name': med['name'],
            'period_days': days,
            'effective_days': effective_days,
            'expected_doses': expected,
            'actual_doses': actual_doses,
            'on_time_doses': on_time_doses,
            'adherence_rate': rate,
            'on_time_rate': on_time_rate,
            'missed_dates': missed[-10:],
        }

    def check_missed_medications(self) -> List[Dict]:
        """
        检查所有活跃药品的漏服情况

        Returns:
            [{"name": "示例降压药", "missed_days": 2, "last_taken": "2026-04-27"}]
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, frequency, start_date FROM medications
            WHERE is_active = 1
        """)
        results = []
        for med in cursor.fetchall():
            adherence = self.get_adherence_rate(med['id'], days=7)
            if adherence and adherence['missed_dates']:
                results.append({
                    'medication_id': med['id'],
                    'name': med['name'],
                    'missed_count': len(adherence['missed_dates']),
                    'missed_dates': adherence['missed_dates'],
                })
        return results

    # ========== 药品余量/过期预警 ==========

    def check_low_stock_medications(self) -> List[Dict]:
        """检查药品余量不足"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name, remaining_quantity, low_stock_threshold, frequency, dose_quantity
            FROM medications
            WHERE is_active = 1 AND remaining_quantity > 0
        """)
        alerts = []
        for row in cursor.fetchall():
            remaining = row['remaining_quantity']
            threshold = row['low_stock_threshold'] or 7
            if remaining <= threshold:
                daily = parse_frequency(row['frequency'])
                dose_qty = row['dose_quantity'] or 1.0
                daily_consumption = daily * dose_qty
                days_left = int(remaining / daily_consumption) if daily_consumption > 0 else 999
                alerts.append({
                    'name': row['name'],
                    'remaining': remaining,
                    'threshold': threshold,
                    'days_left': days_left,
                    'frequency': row['frequency'],
                })
        # 已用完
        cursor.execute("""
            SELECT name, frequency FROM medications
            WHERE is_active = 1 AND remaining_quantity = 0
        """)
        for row in cursor.fetchall():
            alerts.append({
                'name': row['name'],
                'remaining': 0,
                'threshold': 0,
                'days_left': 0,
                'frequency': row['frequency'],
                'alert_type': '已用完'
            })
        return alerts

    def check_expired_medications(self) -> List[Dict]:
        """检查已过期或即将过期（30天内），区分两种状态"""
        conn = self._get_connection()
        cursor = conn.cursor()
        results = []
        # 已过期
        cursor.execute("""
            SELECT name, expiry_date, remaining_quantity
            FROM medications
            WHERE is_active = 1 AND expiry_date < date('now','localtime')
            ORDER BY expiry_date ASC
        """)
        for row in cursor.fetchall():
            results.append({'name': row['name'], 'expiry_date': row['expiry_date'],
                            'remaining': row['remaining_quantity'], 'status': '已过期'})
        # 即将过期（30天内）
        cursor.execute("""
            SELECT name, expiry_date, remaining_quantity
            FROM medications
            WHERE is_active = 1
            AND expiry_date >= date('now','localtime')
            AND expiry_date <= date('now','localtime','+30 days')
            ORDER BY expiry_date ASC
        """)
        for row in cursor.fetchall():
            results.append({'name': row['name'], 'expiry_date': row['expiry_date'],
                            'remaining': row['remaining_quantity'], 'status': '即将过期'})
        return results

    # ========== 每日用药清单与完整性检查 ==========

    def get_daily_med_checklist(self, date: str = None) -> Dict:
        """
        获取指定日期的用药清单（含服用状态）

        多时段药物（如"早,晚"）拆分为独立条目，每个时段一条
        按 schedule_slot 分组排序（早→中→晚→睡前）

        Returns:
            {
                "date": "2026-05-17",
                "total": 5,
                "completed": 3,
                "completion_rate": 60.0,
                "checklist": [...],
                "missing": [...]
            }
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        conn = self._get_connection()
        cursor = conn.cursor()

        # 获取所有活跃药物
        cursor.execute("""
            SELECT id, name, dosage, frequency, remaining_quantity,
                   med_type, schedule_time, end_date, dose_quantity
            FROM medications
            WHERE is_active = 1
            ORDER BY name ASC
        """)
        active_meds = [dict(row) for row in cursor.fetchall()]

        # 过滤：阶段性/临时处方已过 end_date 的排除
        filtered_meds = []
        for med in active_meds:
            if med['med_type'] in ('阶段性', '临时处方') and med['end_date']:
                if med['end_date'] < date:
                    continue
            filtered_meds.append(med)

        # 获取指定日期所有服药记录（含 schedule_slot）
        cursor.execute("""
            SELECT medication_id, time, dosage_taken, is_on_time, schedule_slot
            FROM medication_logs
            WHERE date = ?
        """, (date,))
        logs = [dict(row) for row in cursor.fetchall()]

        # 按 (medication_id, schedule_slot) 建索引
        log_index = {}
        for log in logs:
            key = (log['medication_id'], log['schedule_slot'])
            log_index[key] = log

        SCHEDULE_ORDER = {'早': 0, '中': 1, '晚': 2, '睡前': 3}
        checklist = []
        completed = 0

        for med in filtered_meds:
            schedule_raw = (med['schedule_time'] or '早').strip()
            schedule_parts = [s.strip() for s in schedule_raw.split(',') if s.strip()]
            if not schedule_parts:
                schedule_parts = ['早']

            for slot in schedule_parts:
                key = (med['id'], slot)
                log_entry = log_index.get(key)

                if log_entry:
                    status = '已服'
                    log_time = log_entry['time']
                else:
                    # 也检查无 schedule_slot 的旧记录（向后兼容）
                    legacy_key = (med['id'], None)
                    legacy_entry = log_index.get(legacy_key)
                    if legacy_entry and len(schedule_parts) == 1:
                        status = '已服'
                        log_time = legacy_entry['time']
                    else:
                        status = '未服'
                        log_time = None

                if status == '已服':
                    completed += 1

                checklist.append({
                    'medication_id': med['id'],
                    'name': med['name'],
                    'dosage': med['dosage'],
                    'med_type': med['med_type'] or '长期',
                    'schedule_time': schedule_raw,
                    'schedule_slot': slot,
                    'status': status,
                    'log_time': log_time,
                    'remaining': med['remaining_quantity'],
                    'frequency': med['frequency'],
                })

        # 按 schedule_slot 排序
        checklist.sort(key=lambda x: (SCHEDULE_ORDER.get(x['schedule_slot'], 99), x['name']))

        total = len(checklist)
        rate = round(completed / total * 100, 1) if total > 0 else 0
        missing = [c for c in checklist if c['status'] != '已服']

        return {
            'date': date,
            'total': total,
            'completed': completed,
            'completion_rate': rate,
            'checklist': checklist,
            'missing': missing,
        }

    def check_medication_completeness(self, date: str = None) -> Dict:
        """
        检查当日药物记录完整性，返回提醒信息

        用于"记录服药后"的自动补全提示
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        checklist = self.get_daily_med_checklist(date)
        missing = checklist['missing']

        if not missing:
            return {
                'is_complete': True,
                'message': f'今日({date})药物已全部记录',
                'completion_rate': checklist['completion_rate'],
                'missing': [],
            }

        # 按 schedule_slot 分组提示
        by_schedule = {}
        for m in missing:
            slot = m['schedule_slot']
            if slot not in by_schedule:
                by_schedule[slot] = []
            by_schedule[slot].append(f"{m['name']}({m['dosage']})")

        parts = []
        for schedule in ['早', '中', '晚', '睡前']:
            if schedule in by_schedule:
                parts.append(f"{schedule}: {', '.join(by_schedule[schedule])}")

        message = f"今日({date})还有以下药物未记录 —— {'; '.join(parts)}，是否已服用？"

        return {
            'is_complete': False,
            'message': message,
            'completion_rate': checklist['completion_rate'],
            'missing': missing,
        }

    def batch_log_medications(self, date: str, time: str,
                               schedule_slot: str,
                               medication_ids: List[int],
                               is_on_time: int = 1,
                               notes: str = '') -> List[int]:
        """
        批量记录多种药物的服用

        用于"早上药都吃了"等场景，一键标记指定时段所有药物
        按 schedule_slot 区分，多时段药物每个时段单独记录

        Args:
            date: 服药日期
            time: 服药时间
            schedule_slot: 服药时段（早/中/晚/睡前）
            medication_ids: 药品ID列表
            is_on_time: 是否按时
            notes: 备注

        Returns:
            各药物的 log ID 列表
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        log_ids = []

        for med_id in medication_ids:
            # 获取药品信息
            cursor.execute(
                "SELECT name, dosage, dose_quantity FROM medications WHERE id = ?",
                (med_id,)
            )
            med = cursor.fetchone()
            if not med:
                continue

            # 检查该药该时段是否已记录（按时段区分，避免多时段药物被跳过）
            cursor.execute(
                "SELECT id FROM medication_logs WHERE medication_id = ? AND date = ? AND (schedule_slot = ? OR schedule_slot IS NULL)",
                (med_id, date, schedule_slot)
            )
            if cursor.fetchone():
                continue  # 该时段已记录，跳过

            log = MedicationLog(
                id=None,
                medication_id=med_id,
                date=date,
                time=time,
                dosage_taken=med['dosage'],
                is_on_time=is_on_time,
                notes=notes,
                schedule_slot=schedule_slot,
            )
            log_id = self.log_medication(log)
            log_ids.append(log_id)

        return log_ids

    # ========== 健康日记/症状日志 ==========

    def add_health_log(self, log: HealthLog) -> int:
        """新增健康日记记录"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO health_logs (date, category, title, content, severity)
            VALUES (?, ?, ?, ?, ?)
        """, (log.date, log.category, log.title, log.content, log.severity))
        conn.commit()
        return cursor.lastrowid

    def get_health_logs(self, date: Optional[str] = None, days: int = 30,
                        category: Optional[str] = None) -> List[Dict]:
        """查询健康日志"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if date:
            cursor.execute(
                "SELECT * FROM health_logs WHERE date = ? ORDER BY id DESC", (date,))
        elif category:
            cursor.execute("""
                SELECT * FROM health_logs
                WHERE date >= date('now', ?) AND category = ?
                ORDER BY date DESC, id DESC
            """, (f'-{days} days', category))
        else:
            cursor.execute("""
                SELECT * FROM health_logs
                WHERE date >= date('now', ?)
                ORDER BY date DESC, id DESC
            """, (f'-{days} days',))
        return [dict(row) for row in cursor.fetchall()]

    # ========== 就医待办/复查计划 ==========

    def add_follow_up(self, action: FollowUpAction) -> int:
        """新增就医待办项"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO follow_up_actions
            (title, category, due_date, priority, status, source, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (action.title, action.category, action.due_date,
              action.priority, action.status, action.source, action.notes))
        conn.commit()
        return cursor.lastrowid

    def update_follow_up_status(self, action_id: int, status: str) -> bool:
        """更新就医待办状态"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE follow_up_actions SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (status, action_id))
        conn.commit()
        return cursor.rowcount > 0

    def get_follow_ups(self, status: Optional[str] = None,
                       include_completed: bool = False) -> List[Dict]:
        """查询就医待办列表"""
        conn = self._get_connection()
        cursor = conn.cursor()
        if status:
            cursor.execute("""
                SELECT * FROM follow_up_actions WHERE status = ?
                ORDER BY priority ASC, due_date ASC
            """, (status,))
        elif not include_completed:
            cursor.execute("""
                SELECT * FROM follow_up_actions
                WHERE status != '已完成' AND status != '已取消'
                ORDER BY priority ASC, due_date ASC
            """)
        else:
            cursor.execute("""
                SELECT * FROM follow_up_actions
                ORDER BY status ASC, priority ASC, due_date ASC
            """)
        return [dict(row) for row in cursor.fetchall()]

    def get_overdue_follow_ups(self) -> List[Dict]:
        """获取已过期未完成的待办项"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM follow_up_actions
            WHERE status != '已完成' AND status != '已取消'
            AND due_date IS NOT NULL AND due_date < date('now','localtime')
            ORDER BY priority ASC, due_date ASC
        """)
        return [dict(row) for row in cursor.fetchall()]

    # ========== 指标预警检查 ==========

    def check_alerts(self, metric: DailyMetric) -> List[AlertResult]:
        """对照 thresholds.json 预警阈值检查指标，返回预警列表"""
        threshold_path = os.path.join(os.path.dirname(__file__), 'config', 'thresholds.json')
        if not os.path.exists(threshold_path):
            return []
        with open(threshold_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        ht = config.get('health_thresholds', {})
        severity_map = config.get('alert_rules', {}).get('severity_mapping', {
            'green': '无', 'orange': '轻微', 'red': '中度', 'critical': '严重'
        })
        alerts = []

        # 血压
        bp_cfg = ht.get('blood_pressure', {})
        if metric.systolic_bp is not None and metric.diastolic_bp is not None:
            s, d = metric.systolic_bp, metric.diastolic_bp
            s_level = self._check_range(s, bp_cfg.get('systolic', {}))
            d_level = self._check_range(d, bp_cfg.get('diastolic', {}))
            # 取较严重的级别
            level_order = {'green': 0, 'orange': 1, 'red': 2, 'critical': 3}
            worst_key = max(s_level[0], d_level[0], key=lambda k: level_order.get(k, 0))
            if worst_key != 'green':
                severity = severity_map.get(worst_key, worst_key)
                label = bp_cfg.get('systolic', {}).get(worst_key, {}).get('label', '') or \
                        bp_cfg.get('diastolic', {}).get(worst_key, {}).get('label', '')
                alerts.append(AlertResult('血压', float(s), severity,
                    f'血压 {s}/{d} mmHg，{label}！'))

        # 空腹血糖
        glu_cfg = ht.get('blood_glucose', {}).get('fasting', {})
        if metric.fasting_glucose is not None and glu_cfg:
            fg = metric.fasting_glucose
            level_key, label = self._check_range(fg, glu_cfg)
            if level_key != 'green':
                severity = severity_map.get(level_key, level_key)
                alerts.append(AlertResult('空腹血糖', fg, severity,
                    f'空腹血糖 {fg} mmol/L，{label}！'))

        # 心率
        hr_cfg = ht.get('heart_rate', {}).get('resting', {})
        if metric.heart_rate is not None and hr_cfg:
            hr = metric.heart_rate
            level_key, label = self._check_range(hr, hr_cfg)
            if level_key != 'green':
                severity = severity_map.get(level_key, level_key)
                alerts.append(AlertResult('心率', float(hr), severity,
                    f'静息心率 {hr} bpm，{label}！'))

        # 睡眠
        sleep_cfg = ht.get('sleep_quality', {}).get('duration', {})
        if metric.sleep_hours is not None and sleep_cfg:
            sh = metric.sleep_hours
            level_key, label = self._check_range(sh, sleep_cfg)
            if level_key != 'green':
                severity = severity_map.get(level_key, level_key)
                alerts.append(AlertResult('睡眠', float(sh), severity,
                    f'睡眠时长 {sh} 小时，{label}！'))

        # 步数
        steps_cfg = ht.get('physical_activity', {}).get('daily_steps', {})
        if metric.steps is not None and steps_cfg:
            st = metric.steps
            level_key, label = self._check_range(st, steps_cfg)
            if level_key != 'green':
                severity = severity_map.get(level_key, level_key)
                alerts.append(AlertResult('步数', float(st), severity,
                    f'今日步数 {st}，{label}！'))

        return alerts

    def _check_range(self, value: float, range_config: Dict) -> Tuple[str, str]:
        """
        根据阈值配置判断值所属级别（返回最严重级别）

        当多个区间重叠时（如 red 140-300 与 critical 160-300），
        返回最严重的那个级别

        Returns:
            (level_key, label) 如 ('critical', '严重高血压')
        """
        SEVERITY_ORDER = {'green': 0, 'orange': 1, 'red': 2, 'critical': 3}
        best_key = 'green'
        best_label = '正常'
        best_severity = 0

        for key, cfg in range_config.items():
            if isinstance(cfg, dict) and 'min' in cfg and 'max' in cfg:
                if cfg['min'] <= value <= cfg['max']:
                    base_key = key.split('_')[0] if '_' in key else key
                    if base_key not in ('green', 'orange', 'red', 'critical'):
                        base_key = key
                    severity = SEVERITY_ORDER.get(base_key, 0)
                    if severity > best_severity:
                        best_severity = severity
                        best_key = base_key
                        best_label = cfg.get('label', key)

        return best_key, best_label

    # ========== 统计趋势 ==========

    def get_bp_trend(self, days: int = 30) -> List[Tuple[str, Optional[int], Optional[int]]]:
        """取得血压趋势"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, systolic_bp, diastolic_bp
            FROM daily_metrics
            WHERE date >= date('now', ?)
            AND systolic_bp IS NOT NULL AND diastolic_bp IS NOT NULL
            ORDER BY date ASC
        """, (f'-{days} days',))
        return [(row['date'], row['systolic_bp'], row['diastolic_bp'])
                for row in cursor.fetchall()]

    def get_glucose_trend(self, days: int = 30) -> List[Tuple[str, Optional[float]]]:
        """取得血糖趋势"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, fasting_glucose
            FROM daily_metrics
            WHERE date >= date('now', ?)
            AND fasting_glucose IS NOT NULL
            ORDER BY date ASC
        """, (f'-{days} days',))
        return [(row['date'], row['fasting_glucose']) for row in cursor.fetchall()]

    def get_all_trends(self, days: int = 30) -> Dict[str, List]:
        """获取所有指标的趋势数据（用于仪表盘可视化）"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, systolic_bp, diastolic_bp, heart_rate,
                   fasting_glucose, sleep_hours, steps
            FROM daily_metrics
            WHERE date >= date('now', ?)
            ORDER BY date ASC
        """, (f'-{days} days',))
        rows = cursor.fetchall()
        return {
            'dates': [r['date'] for r in rows],
            'systolic_bp': [r['systolic_bp'] for r in rows],
            'diastolic_bp': [r['diastolic_bp'] for r in rows],
            'heart_rate': [r['heart_rate'] for r in rows],
            'fasting_glucose': [r['fasting_glucose'] for r in rows],
            'sleep_hours': [r['sleep_hours'] for r in rows],
            'steps': [r['steps'] for r in rows],
        }

    # ========== 健康洞察引擎 ==========

    def generate_insights(self, days: int = 30) -> List[HealthInsight]:
        """
        跨表关联分析，生成健康洞察

        综合分析 daily_metrics、medication_logs、health_logs、medical_records
        返回有价值的健康规律和趋势
        """
        insights = []

        # 1. 体检指标跨年变化趋势
        trends = self.get_medical_record_trends()
        for trend in trends:
            values = trend['values']
            if len(values) >= 2:
                first_val = self._parse_numeric(values[0]['value'])
                last_val = self._parse_numeric(values[-1]['value'])
                if first_val is not None and last_val is not None:
                    change = last_val - first_val
                    direction = '上升' if change > 0 else ('下降' if change < 0 else '稳定')
                    pct = abs(round(change / first_val * 100, 1)) if first_val != 0 else 0
                    if change != 0:
                        insights.append(HealthInsight(
                            category='体检趋势',
                            title=f'{trend["item_name"]}{direction}{pct}%',
                            detail=(
                                f'{trend["item_name"]}从 {values[0]["date"]} 的 {values[0]["value"]}'
                                f' {direction}到 {values[-1]["date"]} 的 {values[-1]["value"]}'
                                f'（{values[-1].get("unit","")}），变化{pct}%。'
                            ),
                            confidence=min(0.9, 0.5 + len(values) * 0.1),
                            data_points=len(values),
                        ))

        # 2. 血压与睡眠关联分析
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT date, systolic_bp, diastolic_bp, sleep_hours
            FROM daily_metrics
            WHERE date >= date('now', ?)
            AND systolic_bp IS NOT NULL AND sleep_hours IS NOT NULL
            ORDER BY date ASC
        """, (f'-{days} days',))
        rows = cursor.fetchall()
        if len(rows) >= 5:
            low_sleep = [r['systolic_bp'] for r in rows if r['sleep_hours'] and r['sleep_hours'] < 6]
            normal_sleep = [r['systolic_bp'] for r in rows if r['sleep_hours'] and r['sleep_hours'] >= 7]
            if low_sleep and normal_sleep:
                avg_low = round(sum(low_sleep) / len(low_sleep), 1)
                avg_normal = round(sum(normal_sleep) / len(normal_sleep), 1)
                diff = round(avg_low - avg_normal, 1)
                if abs(diff) >= 5:
                    insights.append(HealthInsight(
                        category='生活习惯',
                        title=f'睡眠不足时收缩压平均{"高" if diff > 0 else "低"}{abs(diff)} mmHg',
                        detail=(
                            f'在最近{days}天中，睡眠不足6小时的日子里'
                            f'收缩压平均为 {avg_low} mmHg，'
                            f'而睡眠充足（>=7小时）时为 {avg_normal} mmHg。'
                            f'差值 {abs(diff)} mmHg。'
                        ),
                        confidence=0.75,
                        data_points=len(rows),
                    ))

        # 3. 症状与指标关联
        cursor.execute("""
            SELECT hl.date, hl.title, dm.systolic_bp, dm.fasting_glucose
            FROM health_logs hl
            LEFT JOIN daily_metrics dm ON hl.date = dm.date
            WHERE hl.date >= date('now', ?)
            AND hl.category = '症状'
            ORDER BY hl.date DESC
        """, (f'-{days} days',))
        symptom_rows = cursor.fetchall()
        if len(symptom_rows) >= 3:
            # 检查有症状的日子血压是否更高
            symptom_bp = [r['systolic_bp'] for r in symptom_rows
                          if r['systolic_bp'] is not None]
            if symptom_bp:
                avg_symptom = round(sum(symptom_bp) / len(symptom_bp), 1)
                # 获取无症状日的血压
                symptom_dates = [r['date'] for r in symptom_rows]
                if symptom_dates:
                    placeholders = ','.join(['?'] * len(symptom_dates))
                    cursor.execute(f"""
                        SELECT AVG(systolic_bp) as avg_bp
                        FROM daily_metrics
                        WHERE date >= date('now', ?)
                        AND systolic_bp IS NOT NULL
                        AND date NOT IN ({placeholders})
                    """, [f'-{days} days'] + symptom_dates)
                    no_symptom = cursor.fetchone()
                    if no_symptom and no_symptom['avg_bp']:
                        avg_no = round(no_symptom['avg_bp'], 1)
                        diff = round(avg_symptom - avg_no, 1)
                        if abs(diff) >= 3:
                            insights.append(HealthInsight(
                                category='症状关联',
                                title=f'有症状日收缩压比无症状日{"高" if diff > 0 else "低"}{abs(diff)} mmHg',
                                detail=(
                                    f'记录症状的日子里收缩压平均 {avg_symptom} mmHg，'
                                    f'无症状日平均 {avg_no} mmHg。'
                                ),
                                confidence=0.65,
                                data_points=len(symptom_bp),
                            ))

        # 4. 用药依从性洞察
        active_meds = self.get_medications(active_only=True)
        for med in active_meds:
            adherence = self.get_adherence_rate(med['id'], days)
            if adherence:
                if adherence['adherence_rate'] < 80:
                    insights.append(HealthInsight(
                        category='用药依从性',
                        title=f'{med["name"]}依从率{adherence["adherence_rate"]}%',
                        detail=(
                            f'{med["name"]}近{days}天应服{adherence["expected_doses"]}次，'
                            f'实际服用{adherence["actual_doses"]}次，'
                            f'依从率{adherence["adherence_rate"]}%。'
                            f'漏服{len(adherence["missed_dates"])}天。'
                        ),
                        confidence=0.95,
                        data_points=adherence['actual_doses'],
                    ))

        return insights

    def _parse_numeric(self, value_str: str) -> Optional[float]:
        """尝试从字符串中提取数值"""
        if not value_str:
            return None
        # 去除常见单位符号
        cleaned = re.sub(r'[^\d.\-]', '', str(value_str))
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return None

    # ========== 每日健康巡检 ==========

    def daily_health_check(self) -> Dict[str, Any]:
        """
        每日健康巡检，汇总所有预警信息

        Returns:
            {
                "date": "2026-04-29",
                "alerts": [...],           # 指标预警
                "medication_alerts": [...], # 药品余量/过期
                "missed_medications": [...],# 漏服
                "overdue_followups": [...], # 过期待办
                "insights": [...],          # 健康洞察
                "yesterday_missing": bool,  # 昨天是否没记录
            }
        """
        today = datetime.now().strftime('%Y-%m-%d')
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

        # 检查昨天是否有指标记录
        yesterday_metric = self.get_daily_metric(yesterday)

        # 指标预警（用今天或最近一次记录）
        alerts = []
        latest = self.get_daily_metric(today) or self.get_daily_metric(yesterday)
        if latest:
            alerts = self.check_alerts(latest)

        return {
            'date': today,
            'yesterday_missing': yesterday_metric is None,
            'alerts': [{'item': a.item, 'level': a.level, 'message': a.message} for a in alerts],
            'medication_alerts': self.check_low_stock_medications() + self.check_expired_medications(),
            'missed_medications': self.check_missed_medications(),
            'medication_completeness': self.check_medication_completeness(today),
            'overdue_followups': self.get_overdue_follow_ups(),
            'insights': [
                {'category': i.category, 'title': i.title,
                 'detail': i.detail, 'confidence': i.confidence}
                for i in self.generate_insights(30)
            ],
        }

    # ========== 关闭连接 ==========

    def close(self) -> None:
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # ========== 数据导出/备份 ==========

    def backup_database(self, backup_dir: str = None) -> str:
        """
        备份数据库文件到指定目录

        Args:
            backup_dir: 备份目录（默认为 Skill 目录下的 backups/）

        Returns:
            备份文件路径
        """
        import shutil

        if backup_dir is None:
            backup_dir = os.path.join(os.path.dirname(__file__), 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"health_log_backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_name)

        # 确保数据已写入后再复制
        conn = self._get_connection()
        conn.commit()
        shutil.copy2(self.db_path, backup_path)

        # 保留最近10个备份，删除更早的
        backups = sorted(
            [f for f in os.listdir(backup_dir) if f.startswith('health_log_backup_') and f.endswith('.db')],
            reverse=True
        )
        for old in backups[10:]:
            os.remove(os.path.join(backup_dir, old))

        return backup_path

    def export_to_json(self, output_path: str = None) -> str:
        """
        导出全部数据为 JSON 文件

        Args:
            output_path: 输出路径（默认为 Skill 目录下的 exports/）

        Returns:
            导出文件路径
        """
        if output_path is None:
            export_dir = os.path.join(os.path.dirname(__file__), 'exports')
            os.makedirs(export_dir, exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            output_path = os.path.join(export_dir, f"health_export_{timestamp}.json")

        conn = self._get_connection()
        cursor = conn.cursor()

        tables = {
            'daily_metrics': 'SELECT * FROM daily_metrics ORDER BY date DESC',
            'medical_records': 'SELECT * FROM medical_records ORDER BY report_date DESC',
            'medications': 'SELECT * FROM medications ORDER BY is_active DESC',
            'medication_logs': 'SELECT * FROM medication_logs ORDER BY date DESC',
            'health_logs': 'SELECT * FROM health_logs ORDER BY date DESC',
            'follow_up_actions': 'SELECT * FROM follow_up_actions ORDER BY priority ASC',
            'lifestyle': 'SELECT * FROM lifestyle',
            'medical_history': 'SELECT * FROM medical_history',
        }

        export_data = {
            'export_time': datetime.now().isoformat(),
            'schema_version': self.get_schema_version(),
            'data': {},
        }

        for table, sql in tables.items():
            try:
                cursor.execute(sql)
                rows = cursor.fetchall()
                export_data['data'][table] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                export_data['data'][table] = []

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2, default=str)

        return output_path


# ========== 测试代码 ==========
if __name__ == "__main__":
    print("=" * 50)
    print("HealthGuardian v2 - 数据库初始化与测试")
    print("=" * 50)

    with DatabaseManager('health_log.db') as db:
        print(f"\n数据库版本: v{db.get_schema_version()}")
        print(f"数据库文件: {db.db_path}")

        # 1. 每日健康巡检
        print("\n--- 每日健康巡检 ---")
        check = db.daily_health_check()
        print(f"日期: {check['date']}")
        print(f"昨日未记录: {'是' if check['yesterday_missing'] else '否'}")
        if check['alerts']:
            print("指标预警:")
            for a in check['alerts']:
                print(f"  [{a['level']}] {a['message']}")
        else:
            print("指标预警: 无")
        if check['medication_alerts']:
            print("药品预警:")
            for m in check['medication_alerts']:
                atype = m.get('alert_type', f'剩余{m["remaining"]}片')
                print(f"  {m['name']}: {atype}")
        if check['missed_medications']:
            print("漏服:")
            for m in check['missed_medications']:
                print(f"  {m['name']}: 漏服{m['missed_count']}天")
        if check['overdue_followups']:
            print("过期待办:")
            for f in check['overdue_followups']:
                print(f"  [{f['priority']}] {f['title']} (截止: {f['due_date']})")

        # 2. 健康洞察
        print("\n--- 健康洞察 ---")
        insights = db.generate_insights(30)
        if insights:
            for i in insights:
                print(f"  [{i.category}] {i.title} (置信度: {i.confidence})")
        else:
            print("  暂无足够数据生成洞察")

        # 3. 用药依从性
        print("\n--- 用药依从性 ---")
        active_meds = db.get_medications(active_only=True)
        for med in active_meds:
            adherence = db.get_adherence_rate(med['id'], days=30)
            if adherence:
                print(f"  {adherence['medication_name']}: "
                      f"依从率 {adherence['adherence_rate']}%, "
                      f"按时率 {adherence['on_time_rate']}%")

        # 4. 每日用药清单
        print("\n--- 每日用药清单 ---")
        checklist = db.get_daily_med_checklist()
        print(f"  日期: {checklist['date']}")
        print(f"  完成率: {checklist['completion_rate']}% ({checklist['completed']}/{checklist['total']})")
        for item in checklist['checklist']:
            status_icon = {'已服': '✓', '未服': '✗', '部分': '◐'}.get(item['status'], '?')
            print(f"  {status_icon} {item['name']} [{item['schedule_time']}] {item['status']} {item.get('log_time', '')}")

        # 5. 药物完整性检查
        print("\n--- 药物完整性检查 ---")
        completeness = db.check_medication_completeness()
        print(f"  完整: {'是' if completeness['is_complete'] else '否'}")
        if not completeness['is_complete']:
            print(f"  提示: {completeness['message']}")

    print("\n" + "=" * 50)
    print("测试完成！")

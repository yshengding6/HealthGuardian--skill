# HealthGuardian v3

个人健康守护者 - 基于 SQLite + 多记忆架构 + AI 的个人健康自进化智能体

## 功能概览

| 模块 | 功能 | 版本 |
|------|------|------|
| **VitalsTracker** | 记录每日血压、血糖、心率、睡眠、步数，自动预警 | v1 |
| **HealthDiary** | 健康日记/症状日志，与指标数据分离 | v1 |
| **MedReportAnalyzer** | 解析体检报告（图片 OCR + PDF 文本提取） | v1 |
| **MedTracker** | 药品闭环管理、用药清单制、完整性检查、批量记录 | v3 |
| **HealthConsultant** | 健康分析与预警（9 大品类阈值） | v1 |
| **InsightEngine** | 跨表关联分析（药效-指标/症状-指标/体检趋势） | v2 |
| **FollowUpTracker** | 就医待办/复查计划、过期预警 | v1 |
| **MemoryManager** | 三层记忆架构（语义/情景/规则）、经验自动提取 | v2 |
| **DailyCheck** | 每日健康巡检一键汇总 | v2 |
| **Dashboard** | 固定三区布局 HTML 仪表盘 | v3 |

## 项目结构

```
HealthGuardian-Skill/
├── db_manager.py           # 数据库管理核心模块 v3 (Schema v6)
├── dashboard.py            # 固定格式健康仪表盘 v3
├── memory_manager.py       # 记忆管理模块 (三层记忆架构)
├── med_report_analyzer.py  # 图片体检报告解析 (PIL + AI Vision)
├── pdf_report_parser.py    # PDF 体检报告解析 (PyMuPDF)
├── import_records.py       # 历史数据导入工具
├── SKILL.md                # Skill 完整文档
├── config/
│   └── thresholds.json     # 预警阈值配置 (9 大品类)
├── prompts/
│   └── ocr_template.txt    # OCR 识别提示词模板
├── memory/
│   ├── health-patterns.example.json  # 语义记忆模板
│   └── episodic/                     # 情景记忆目录
└── reports/
    └── 健康档案汇总.md      # 健康档案模板
```

## 数据库架构 (Schema v6)

9 张表，版本化自动迁移：

| 表名 | 用途 |
|------|------|
| `daily_metrics` | 每日数值指标（血压/血糖/心率/睡眠/步数） |
| `health_logs` | 健康日记/症状日志 |
| `medical_records` | 体检报告异常项 |
| `medications` | 药品管理（含类型/时段/疗程截止） |
| `medication_logs` | 服药记录（含时段 slot） |
| `lifestyle` | 生活习惯档案 |
| `medical_history` | 病史记录 |
| `follow_up_actions` | 就医待办/复查计划 |
| `_meta` | Schema 版本元数据 |

## 快速开始

### 安装依赖

```bash
pip install Pillow PyMuPDF
```

### 记录每日指标

```python
from db_manager import DatabaseManager, DailyMetric

with DatabaseManager("health_log.db") as db:
    # 增量更新：只覆盖非 NULL 字段，保留已有数据
    metric = DailyMetric(
        id=None, date="2026-05-17",
        systolic_bp=125, diastolic_bp=82, heart_rate=72
    )
    db.add_daily_metric(metric)

    # 自动预警
    alerts = db.check_alerts(metric)
    for a in alerts:
        print(f"[{a.level}] {a.message}")
```

### 用药清单制（v3 新增）

```python
with DatabaseManager("health_log.db") as db:
    # 查看今日用药清单（多时段药物拆分显示）
    checklist = db.get_daily_med_checklist()
    print(f"完成率: {checklist['completion_rate']}%")
    for item in checklist['checklist']:
        print(f"  [{item['status']}] {item['name']} ({item['schedule_slot']})")

    # 批量记录早间药物
    db.batch_log_medications(
        date="2026-05-17", time="06:30",
        schedule_slot="早",
        medication_ids=[1, 7]
    )

    # 记录后自动检查遗漏
    comp = db.check_medication_completeness()
    if not comp['is_complete']:
        print(comp['message'])
```

### 生成健康仪表盘

```bash
python dashboard.py
# 输出: dashboard.html（固定三区布局）
```

仪表盘布局：
1. **优先区** - 最新指标 + 预警横幅 + 用药完成率
2. **用药区** - 今日清单(按时段分组) + 依从率进度条
3. **详情区** - 趋势图 + 就医待办 + 健康日志

## 药物管理字段 (v3 新增)

| 字段 | 说明 | 示例 |
|------|------|------|
| `med_type` | 长期/阶段性/临时处方 | 长期 |
| `schedule_time` | 服药时段（多选用逗号分隔） | 早,晚 |
| `end_date` | 疗程结束日期（阶段性用） | 2026-08-15 |
| `schedule_slot` | 每次记录的时段(v6) | 晚 |

## 预警阈值标准

基于 `config/thresholds.json`，9 大品类：

| 指标 | 正常 | 轻微 | 中度 | 严重 |
|------|------|------|------|------|
| 收缩压 | <120 | 120-139 | 140-159 | ≥160 |
| 舒张压 | <80 | 80-89 | 90-99 | ≥100 |
| 空腹血糖 | 3.9-5.5 | 5.6-6.9 | 7.0-11.0 | ≥11.1 |
| 心率 | 60-100 | 50-59/101-110 | <50/>110 | - |

## 自我进化协议

```
用户操作 → 记录数据 → 生成洞察 → 提取经验 → 更新记忆 → 改进预警
```

- 记录指标后自动检查预警和新趋势
- 服药记录后自动检查完整性遗漏
- 同类经验出现 5+ 次自动提升为语义记忆模式
- 三层记忆：语义记忆(规律) + 情景记忆(事件) + 健康规则(约束)

## 授权

MIT License

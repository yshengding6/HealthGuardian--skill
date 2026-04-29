# HealthGuardian v2 - 个人健康守护者（逆熵进化版）

基于 SQLite + 多记忆架构 + AI 的个人健康自进化智能体。整合每日指标追踪、体检报告归档、药品闭环管理、健康预警、就医计划、跨表洞察。

## 触发词

"记录健康指标"、"记一下今天的血压/血糖/心率/睡眠/步数"、"解析体检报告"、"分析体检单"、"查看健康趋势"、"健康周报"、"添加药品"、"用药提醒"、"健康预警"、"记个健康日记"、"就医计划"、"复查清单"、"健康巡检"、"HealthGuardian"、"吃药了"、"健康仪表盘"

## 工作目录

所有操作在 skill 目录下进行：`~/.workbuddy/skills/HealthGuardian/`

## 体检报告存储

所有体检报告文件统一存储在 `reports/` 目录下：
- PDF原件：`reports/*.pdf`（用户的体检报告、基因检测报告等，**不纳入开源仓库**）
- 健康档案汇总：`reports/健康档案汇总.md`（模板，不含真实数据）
- 健康档案汇总：`reports/健康档案汇总.md`
- **约定**：凡是用户提供的体检报告、基因检测报告等健康相关文档，一律复制到 `reports/` 目录归档保存

## 核心模块

### 1. VitalsTracker - 每日指标追踪
- 使用 `db_manager.py` 的 `DatabaseManager` 和 `DailyMetric` 类
- 支持记录：血压、心率、空腹血糖、睡眠时长/质量、步数
- **记录后自动预警**：`db.check_alerts(metric)` 对照 `config/thresholds.json` 即时判断
- 自然语言输入，用户随口说即可

### 2. HealthDiary - 健康日记/症状日志
- 使用 `db_manager.py` 的 `HealthLog` 类和 `health_logs` 表
- 与 `daily_metrics`（纯数值）分离，专用于记录症状、就诊经历、用药变化等文字描述
- 分类：症状 / 就诊 / 用药 / 其他

### 3. MedReportAnalyzer - 体检报告解析
- 图片报告：使用 `med_report_analyzer.py`（PIL预处理 + AI Vision OCR）
- PDF报告：使用 `pdf_report_parser.py`（PyMuPDF提取文本）
- 解析后异常项写入 `medical_records` 表
- **推荐做法**：PDF报告先用 PyMuPDF 提取全文，AI 阅读理解后结构化写入数据库

### 4. MedTracker - 药品闭环管理（v2 新增）
- **药品管理**：记录名称、剂量、频率、库存、有效期、低库存预警阈值
- **服药日志**：`medication_logs` 表记录每次实际服药（时间、剂量、是否按时）
- **依从性计算**：`db.get_adherence_rate(med_id)` 自动计算依从率和按时率
- **漏服检测**：`db.check_missed_medications()` 自动发现漏服
- **记录服药时自动扣减库存**：`db.log_medication(med_log)` 一步到位
- **药品余量/过期预警**：`db.check_low_stock_medications()` + `db.check_expired_medications()`

### 5. HealthConsultant - 健康分析与预警
- 使用 `config/thresholds.json` 中的预警阈值标准（9大品类）
- 血压：正常(<120/80) / 偏高(120-139/80-89) / 高血压(>=140/90) / 危险(>=180/110)
- 血糖：正常(<5.6) / 注意(5.6-6.0) / 糖尿病前期(6.1-6.9) / 糖尿病(>=7.0)
- 心率：偏低(<50) / 正常(60-100) / 偏高(>100)
- **每次记录指标后自动调用 `check_alerts()`**

### 6. InsightEngine - 健康洞察引擎（v2 新增）
- **跨表关联分析**：`db.generate_insights(days)` 综合分析多张表
- 药效关联：分析用药与指标变化的因果关系
- 症状-指标关联：有症状日与无症状日的指标对比
- 体检趋势：跨年体检指标变化追踪
- 生活习惯影响：睡眠、运动等与指标的关联
- 返回 `HealthInsight` 对象列表，含置信度评分

### 7. FollowUpTracker - 就医待办/复查计划
- 使用 `db_manager.py` 的 `FollowUpAction` 类和 `follow_up_actions` 表
- 记录待复查/就诊/检验事项，含优先级和截止日期
- **过期预警**：`db.get_overdue_follow_ups()` 自动检查过期待办

### 8. MemoryManager - 多记忆架构（v2 新增）
- **语义记忆**（`memory/health-patterns.json`）：健康规律与模式库，跨会话可复用
- **情景记忆**（`memory/episodic/`）：具体健康事件记录，按年归档
- **健康规则**（嵌入语义记忆）：血压控制/血糖管理/用药安全等规则
- **经验提取**：`mm.extract_and_learn()` 从事件中自动提取模式
- 借鉴 self-improving-agent 的三层记忆设计

### 9. DailyCheck - 每日健康巡检（v2 新增）
- `db.daily_health_check()` 一键获取当日健康全貌
- 检查昨日是否记录指标
- 汇总所有预警（指标/药品/漏服/过期待办）
- 生成健康洞察摘要

### 10. Dashboard - 交互式健康仪表盘（v2 新增）
- 使用 `dashboard.py` 生成 HTML 可视化仪表盘
- 血压/血糖/心率的趋势折线图
- 用药依从率统计
- 就医待办看板
- 通过 `preview_url` 在 WorkBuddy 中查看

## 数据库

- SQLite 数据库文件：`health_log.db`（自动创建，自动迁移）
- **Schema 版本管理**：`_meta` 表记录版本号，`_migrate_database()` 自动执行增量迁移
- 当前版本：**v4**
- **8张表**：

| 表名 | 用途 | 版本 |
|------|------|------|
| `_meta` | Schema 版本元数据 | v2 |
| `daily_metrics` | 每日数值指标（血压/血糖/心率/睡眠/步数） | v1 |
| `health_logs` | 健康日记/症状日志（文字描述） | v1 |
| `medical_records` | 体检报告异常项 | v1 |
| `medications` | 药品管理（名称/剂量/库存/有效期/每次服用片数） | v4 |
| `medication_logs` | 服药记录（时间/剂量/是否按时） | v3 |
| `lifestyle` | 生活习惯档案 | v1 |
| `medical_history` | 病史记录 | v1 |
| `follow_up_actions` | 就医待办/复查计划 | v1 |

## 操作流程

### 记录每日指标
1. 解析用户自然语言输入
2. 使用 Python 执行 db_manager.py 写入 `daily_metrics` 表
3. **自动调用 `db.check_alerts(metric)` 进行预警判断**
4. 反馈记录结果和预警信息

### 记录服药（v2 新增）
1. 用户说"吃了药"或"吃药了"
2. 调用 `db.log_medication(MedicationLog(...))` 记录服药并自动扣减库存
3. 返回依从率信息

### 记录健康日记
1. 用户描述症状、就诊经历等
2. 写入 `health_logs` 表
3. 严重症状同时更新就医待办

### 解析体检报告
1. PDF报告：用 PyMuPDF 提取文本 → AI 阅读理解 → 结构化写入 `medical_records`
2. 图片报告：用 med_report_analyzer.py 预处理 → AI Vision OCR → 写入数据库
3. 新异常项同步添加到 `follow_up_actions` 就医待办

### 每日健康巡检（v2 新增）
1. 调用 `db.daily_health_check()`
2. 汇总：昨日记录检查 + 指标预警 + 药品预警 + 漏服 + 过期待办 + 健康洞察
3. 以简洁摘要形式反馈给用户

### 生成健康洞察（v2 新增）
1. 调用 `db.generate_insights(30)` 获取近30天洞察
2. 调用 `mm.get_patterns()` 获取已知健康规律
3. 结合语义记忆和数据库数据，给出综合健康建议

### 健康仪表盘（v2 新增）
1. 调用 `python dashboard.py` 生成 HTML
2. 用 `preview_url` 在 WorkBuddy 中查看

## 自我进化协议（v2 新增）

借鉴 self-improving-agent 的方法论，每次 HealthGuardian 操作后自动执行：

### 进化闭环

```
用户操作 → 记录数据 → 生成洞察 → 提取经验 → 更新记忆 → 改进预警
    │           │          │           │          │          │
    ▼           ▼          ▼           ▼          ▼          ▼
  触发词    daily_metrics  Insights   episodic  semantic  thresholds
```

### 具体规则

1. **记录指标后**：检查该指标是否触发了新趋势，如果有则提取情景记忆
2. **体检解析后**：与上次体检对比，标注变化方向，记录为经验
3. **服药记录后**：更新依从率，如果依从率下降则生成提醒模式
4. **健康日记后**：检查是否与近期指标异常相关联
5. **模式积累**：同类经验出现 3+ 次自动提升为语义记忆模式

### 进化标记格式

```markdown
<!-- Evolution: YYYY-MM-DD | source: daily_metrics | insight: 描述 -->
```

## 使用 Python 执行

```bash
cd ~/.workbuddy/skills/HealthGuardian && python -c "
from db_manager import DatabaseManager, DailyMetric, MedicationLog
from memory_manager import MemoryManager

db = DatabaseManager('health_log.db')
mm = MemoryManager()

# 记录指标 + 预警
metric = DailyMetric(None, '2026-04-29', 125, 82, 72, 5.8, 7.5, 4, 8000, '')
db.add_daily_metric(metric)
alerts = db.check_alerts(metric)
for a in alerts:
    print(f'[{a.level}] {a.message}')

# 记录服药（自动扣库存）
log = MedicationLog(None, 1, '2026-04-29', '07:30', '2.5mg', 1, '')
db.log_medication(log)

# 每日健康巡检
check = db.daily_health_check()
print(f'昨日未记录: {check[\"yesterday_missing\"]}')
print(f'漏服药品: {len(check[\"missed_medications\"])}种')
print(f'过期待办: {len(check[\"overdue_followups\"])}项')

# 健康洞察
for insight in db.generate_insights(30):
    print(f'[{insight.category}] {insight.title}')

# 记忆摘要
summary = mm.get_memory_summary()
print(f'记忆库: {summary[\"total_patterns\"]}个模式, {summary[\"total_episodic\"]}条事件')

db.close()
"
```

## 文件清单

| 文件 | 用途 |
|------|------|
| `db_manager.py` | 数据库管理核心模块 v2（数据类 + CRUD + 预警 + 洞察引擎 + 巡检 + 备份/导出） |
| `memory_manager.py` | 记忆管理模块（三层记忆架构 + 经验提取） |
| `dashboard.py` | HTML 健康仪表盘生成器（Chart.js 可视化） |
| `med_report_analyzer.py` | 图片体检报告解析（PIL预处理 + AI Vision） |
| `pdf_report_parser.py` | PDF体检报告文本提取解析（PyMuPDF） |
| `config/thresholds.json` | 预警阈值配置（9大品类） |
| `prompts/ocr_template.txt` | OCR识别提示词模板 |
| `memory/health-patterns.json` | 语义记忆（健康规律与模式库） |
| `memory/episodic/` | 情景记忆（按年归档的健康事件） |
| `reports/健康档案汇总.md` | 结构化健康档案（最核心的参考文档） |
| `reports/*.pdf` | 体检报告/基因检测PDF原件 |

## 注意事项

- 健康数据属于用户隐私，不得外传
- AI 分析仅供参考，不能替代专业医疗建议
- 预警为提醒性质，严重指标建议就医
- daily_metrics 同一天的数据使用 INSERT OR REPLACE 覆盖更新
- 每次记录指标后**必须**调用 check_alerts() 检查预警
- 每次操作完成后执行 daily_health_check() 检查全局状态
- **服药记录使用 log_medication()**，不要手动 update_medication_quantity()
- log_medication() 会根据 `medications.dose_quantity` 动态扣减库存（每次1片/2片/半片等）
- check_alerts() 统一读取 `config/thresholds.json` 配置，不要硬编码阈值
- 记忆数据在 `memory/` 目录下，定期回顾和清理过时模式
- **定期备份数据库**：`db.backup_database()` 或 `db.export_to_json()`

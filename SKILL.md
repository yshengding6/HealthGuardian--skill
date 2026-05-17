# HealthGuardian v3 - 个人健康守护者（逆熵进化版）

基于 SQLite + 多记忆架构 + AI 的个人健康自进化智能体。整合每日指标追踪、体检报告归档、药品闭环管理、健康预警、就医计划、跨表洞察。v3 新增：用药清单制、完整性检查、固定格式仪表盘。

## 触发词

"记录健康指标"、"记一下今天的血压/血糖/心率/睡眠/步数"、"解析体检报告"、"分析体检单"、"查看健康趋势"、"健康周报"、"添加药品"、"用药提醒"、"健康预警"、"记个健康日记"、"就医计划"、"复查清单"、"健康巡检"、"HealthGuardian"、"吃药了"、"健康仪表盘"

## 工作目录

所有操作在 skill 目录下进行：`~/.workbuddy/skills/HealthGuardian/`

## 体检报告存储

所有体检报告文件统一存储在 `reports/` 目录下：
- PDF原件：`reports/*.pdf`（用户的体检报告、基因检测报告等，**不纳入开源仓库**）
- 健康档案汇总：`reports/健康档案汇总.md`（模板，不含真实数据）
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

### 4. MedTracker - 药品闭环管理（v3 增强用药清单制）
- **药品管理**：记录名称、剂量、频率、库存、有效期、低库存预警阈值
- **药物分类**（v3 新增）：`med_type` 字段区分 长期/阶段性/临时处方
- **服药时段**（v3 新增）：`schedule_time` 字段 早/中/晚/睡前，多选用逗号分隔
- **疗程截止**（v3 新增）：`end_date` 字段，阶段性/临时处方药的结束日期
- **服药日志**：`medication_logs` 表记录每次实际服药（时间、剂量、是否按时）
- **依从性计算**：`db.get_adherence_rate(med_id)` 自动计算依从率和按时率
- **漏服检测**：`db.check_missed_medications()` 自动发现漏服
- **记录服药时自动扣减库存**：`db.log_medication(med_log)` 一步到位
- **药品余量/过期预警**：`db.check_low_stock_medications()` + `db.check_expired_medications()`
- **每日用药清单**（v3 新增）：`db.get_daily_med_checklist(date)` 按时段分组，标注已服/未服
- **完整性检查**（v3 新增）：`db.check_medication_completeness(date)` 记录后自动检查遗漏
- **批量记录**（v3 新增）：`db.batch_log_medications(date, time, med_ids)` 一键标记多药

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

### 10. Dashboard - 固定格式健康仪表盘（v3 重构）
- 使用 `dashboard.py` 生成 HTML 可视化仪表盘
- **固定三区布局**，优先级从上到下：
  - **第一区·优先区**：最新指标大数字（血压/心率/血糖/用药完成率）+ 预警横幅（关键→一般）
  - **第二区·用药区**：今日用药清单（按时段分组）+ 依从率进度条
  - **第三区·详情区**：血压趋势图 + 心率/血糖图 + 就医待办 + 健康日志
- **固定设计规范**：配色、字体、区块顺序固定，不随会话变化
- 通过 `preview_url` 在 WorkBuddy 中查看

## 数据库

- SQLite 数据库文件：`health_log.db`（自动创建，自动迁移）
- **Schema 版本管理**：`_meta` 表记录版本号，`_migrate_database()` 自动执行增量迁移
- 当前版本：**v6**
- **9张表**：

| 表名 | 用途 | 版本 |
|------|------|------|
| `_meta` | Schema 版本元数据 | v2 |
| `daily_metrics` | 每日数值指标（血压/血糖/心率/睡眠/步数） | v1 |
| `health_logs` | 健康日记/症状日志（文字描述） | v1 |
| `medical_records` | 体检报告异常项 | v1 |
| `medications` | 药品管理（名称/剂量/库存/有效期/每次服用片数/药物类型/服药时段/疗程截止） | v5 |
| `medication_logs` | 服药记录（时间/剂量/是否按时/时段slot） | v6 |
| `lifestyle` | 生活习惯档案 | v1 |
| `medical_history` | 病史记录 | v1 |
| `follow_up_actions` | 就医待办/复查计划 | v1 |

## 操作流程

### 记录每日指标
1. 解析用户自然语言输入
2. 使用 Python 执行 db_manager.py 写入 `daily_metrics` 表
3. **自动调用 `db.check_alerts(metric)` 进行预警判断**
4. 反馈记录结果和预警信息

### 记录服药（v3 增强：清单制 + 完整性检查）
1. 用户说"吃了药"或"吃药了"或"早上的药都吃了"
2. 如果是批量（"早上的药都吃了"）：调用 `db.batch_log_medications(date, time, medication_ids)` 一键标记该时段所有药物
3. 如果是单药：调用 `db.log_medication(MedicationLog(...))` 记录并扣减库存
4. **自动执行 `db.check_medication_completeness(date)`**
5. 如有未记录药物，主动提示："今天还有以下药物未记录：XXX(晚)，是否已服用？"
6. 用户确认后批量补录

### 记录健康日记
1. 用户描述症状、就诊经历等
2. 写入 `health_logs` 表
3. 严重症状同时更新就医待办

### 解析体检报告
1. PDF报告：用 PyMuPDF 提取文本 → AI 阅读理解 → 结构化写入 `medical_records`
2. 图片报告：用 med_report_analyzer.py 预处理 → AI Vision OCR → 写入数据库
3. 新异常项同步添加到 `follow_up_actions` 就医待办

### 每日健康巡检（v3 增强）
1. 调用 `db.daily_health_check()`
2. 汇总：昨日记录检查 + 指标预警 + 药品预警 + 漏服 + **药物完成率** + 过期待办 + 健康洞察
3. 以简洁摘要形式反馈给用户

### 生成健康洞察（v2 新增）
1. 调用 `db.generate_insights(30)` 获取近30天洞察
2. 调用 `mm.get_patterns()` 获取已知健康规律
3. 结合语义记忆和数据库数据，给出综合健康建议

### 健康仪表盘（v3 固定格式）
1. 调用 `python dashboard.py` 生成 HTML
2. 固定三区布局：优先区(指标+预警) → 用药区(清单+依从率) → 详情区(图表+日志)
3. 用 `preview_url` 在 WorkBuddy 中查看

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
3. **服药记录后**：更新依从率，如果依从率下降则生成提醒模式；**自动调用 `check_medication_completeness()` 检查遗漏并提示**
4. **健康日记后**：检查是否与近期指标异常相关联
5. **模式积累**：同类经验出现 3+ 次自动提升为语义记忆模式

### 进化标记格式

```markdown
<!-- Evolution: YYYY-MM-DD | source: daily_metrics | insight: 描述 -->
```

## 用药清单协议（v3 新增）

为解决药物记录不完整问题，v3 引入清单制。所有操作必须遵守以下协议：

### 添加新药规则
- **必须**填写 `med_type`（长期/阶段性/临时处方）
- **必须**填写 `schedule_time`（早/中/晚/睡前，多选用逗号分隔如"早,晚"）
- 阶段性/临时处方**必须**填写 `end_date`（疗程结束日期）
- 长期药的 `end_date` 为 NULL

### 记录服药规则
1. 每次记录服药后**必须**调用 `check_medication_completeness(date)` 检查遗漏
2. 如有未记录药物，**必须**主动提示用户："今天还有以下药物未记录：XXX，是否已服用？"
3. 用户说"早上的药都吃了"等批量描述时，使用 `batch_log_medications()` 一键标记
4. 批量记录会自动跳过已记录的药物，不会重复

### 每日巡检规则
- 巡检结果新增 `medication_completeness` 字段，包含当日药物完成率和未记录清单
- 巡检时如有未完成药物，需在摘要中突出提示

### 药物类型与时段对照
| med_type | 说明 | schedule_time 示例 | end_date |
|----------|------|-------------------|----------|
| 长期 | 需持续服用的慢性病药物 | 早 | NULL |
| 阶段性 | 有明确疗程的处方药 | 晚 | 2026-08-15 |
| 临时处方 | 短期处方药（抗生素等） | 早,中,晚 | 2026-05-25 |

## 仪表盘固定格式规范（v3 新增）

仪表盘采用**固定三区布局**，优先级从上到下，格式不随会话变化：

### 第一区·优先区（Always Visible First）
- 4 个大数字卡片：最新血压、最新心率、最新血糖、用药完成率（进度条+百分比）
- 预警横幅：关键预警（红底）→ 一般预警（橙底），无预警时绿色"系统正常"
- 此区永远在顶部

### 第二区·用药区
- 今日用药清单：按时段分4组（早/中/晚/睡前），每条标注已服/未服/部分
- 依从率进度条：各药30天依从率，绿(≥80%)/橙(50-80%)/红(<50%)

### 第三区·详情区
- 血压趋势折线图（全宽）
- 心率/血糖趋势图（并排）
- 就医待办 + 健康日志（并排）

### 固定设计规范
- 配色：深蓝黑背景(#0a0e17)、蓝色主色(#38bdf8)、绿色正常(#2ed573)、橙色警告(#ffa502)、红色危险(#ff4757)
- 字体：数字/英文用 Rajdhani，中文用 PingFang SC / Microsoft YaHei
- 区块之间用分隔线和区域标签（优先区/用药区/详情区）明确区分

## 使用 Python 执行

### Windows PowerShell 执行方式（推荐）

由于 PowerShell 不支持 `&&` 链接符和 bash 风格的 `-c` 引号嵌套，需使用 Start-Process 方式执行：

1. **写一个临时 .py 脚本**到 skill 目录
2. **用 Start-Process 执行**，输出重定向到文件
3. **读取输出文件**获取结果

示例（记录血压指标）：
```python
# 写入脚本文件
script_content = '''
import sys
sys.path.insert(0, "C:/Users/老丁的电脑/.workbuddy/skills/HealthGuardian")
from db_manager import DatabaseManager, DailyMetric

db = DatabaseManager("health_log.db")
metric = DailyMetric(
    id=None,
    date="2026-04-29",
    systolic_bp=125,
    diastolic_bp=82,
    heart_rate=72,
    fasting_glucose=None,
    sleep_hours=None,
    sleep_quality=None,
    steps=None,
    notes=""
)
db.add_daily_metric(metric)
alerts = db.check_alerts(metric)
for a in alerts:
    print(f"[{a.level}] {a.message}")
check = db.daily_health_check()
print(f"昨日未记录: {check['yesterday_missing']}")
print(f"漏服药品: {len(check['missed_medications'])}种")
db.close()
'''
with open("C:/Users/老丁的电脑/.workbuddy/skills/HealthGuardian/_temp_hg.py", "w", encoding="utf-8") as f:
    f.write(script_content)
```

```powershell
# 执行脚本（不弹出窗口，结果输出到文件）
Start-Process -FilePath "C:\Program Files\Python313\python.exe" `
    -ArgumentList "C:\Users\老丁的电脑\.workbuddy\skills\HealthGuardian\_temp_hg.py" `
    -NoNewWindow -Wait `
    -RedirectStandardOutput "C:\Users\老丁的电脑\.workbuddy\skills\HealthGuardian\_out.txt" `
    -RedirectStandardError "C:\Users\老丁的电脑\.workbuddy\skills\HealthGuardian\_err.txt" `
    -WorkingDirectory "C:\Users\老丁的电脑\.workbuddy\skills\HealthGuardian"
```

```python
# 读取输出
with open("C:/Users/老丁的电脑/.workbuddy/skills/HealthGuardian/_out.txt", "r", encoding="utf-8") as f:
    print(f.read())
```

### 关键数据类字段对照

**DailyMetric**（每日指标）：
```
id, date, systolic_bp, diastolic_bp, heart_rate,
fasting_glucose, sleep_hours, sleep_quality, steps, notes
```

**MedicationLog**（服药记录）：
```
id, medication_id, date, time, dosage_taken, is_on_time, notes, schedule_slot
```
- medication_id=1 对应"施惠达"
- is_on_time=1 表示按时，0 表示迟到
- schedule_slot=该次记录对应的服药时段（早/中/晚/睡前），v6新增

**Medication**（药品）新增字段（v3）：
```
med_type: '长期'/'阶段性'/'临时处方'
schedule_time: '早'/'中'/'晚'/'睡前'（多选用逗号分隔）
end_date: '2026-08-15'（阶段性/临时处方的疗程结束日期，长期药为NULL）
```

### 常见操作示例

**记录每日指标：**
```python
metric = DailyMetric(
    id=None, date="2026-04-29",
    systolic_bp=125, diastolic_bp=82, heart_rate=72,
    fasting_glucose=None, sleep_hours=None,
    sleep_quality=None, steps=None, notes=""
)
db.add_daily_metric(metric)
```

**记录服药：**
```python
log = MedicationLog(
    id=None, medication_id=1,
    date="2026-04-29", time="07:30",
    dosage_taken="2.5mg", is_on_time=1, notes=""
)
db.log_medication(log)
# 记录后必须检查完整性
completeness = db.check_medication_completeness("2026-04-29")
if not completeness['is_complete']:
    print(completeness['message'])
```

**批量记录服药（v3 新增）：**
```python
# 用户说"早上的药都吃了"
log_ids = db.batch_log_medications(
    date="2026-05-17", time="06:30",
    schedule_slot="早",  # 指定时段
    medication_ids=[1, 7]  # 施惠达、碳酸钙D3
)
# 自动跳过该时段已记录的药物
```

**查看每日用药清单（v3 新增）：**
```python
checklist = db.get_daily_med_checklist("2026-05-17")
print(f"完成率: {checklist['completion_rate']}%")
for item in checklist['checklist']:
    print(f"  {item['status']} {item['name']} [{item['schedule_slot']}]")
if checklist['missing']:
    print(f"未记录: {', '.join(m['name'] + '(' + m['schedule_slot'] + ')' for m in checklist['missing'])}")
```

### 不需要清理临时文件

临时文件（`_temp_hg.py`, `_out.txt`, `_err.txt`）下次执行会自动覆盖，无需手动删除。**不要使用 rm/Remove-Item 删除文件**，否则会触发 WorkBuddy 安全确认框。

## 文件清单

| 文件 | 用途 |
|------|------|
| `db_manager.py` | 数据库管理核心模块 v3（数据类 + CRUD + 预警 + 洞察引擎 + 巡检 + 清单制 + 完整性检查 + 备份/导出） |
| `memory_manager.py` | 记忆管理模块（三层记忆架构 + 经验提取） |
| `dashboard.py` | HTML 健康仪表盘生成器 v3（固定三区布局 + Chart.js 可视化） |
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
- daily_metrics 同一天的数据使用**增量更新**（只覆盖非 NULL 字段，保留已有数据）
- 每次记录指标后**必须**调用 check_alerts() 检查预警
- 每次操作完成后执行 daily_health_check() 检查全局状态
- **服药记录使用 log_medication()**，不要手动 update_medication_quantity()
- log_medication() 会根据 `medications.dose_quantity` 动态扣减库存（每次1片/2片/半片等）
- check_alerts() 统一读取 `config/thresholds.json` 配置，不要硬编码阈值
- 记忆数据在 `memory/` 目录下，定期回顾和清理过时模式
- **定期备份数据库**：`db.backup_database()` 或 `db.export_to_json()`

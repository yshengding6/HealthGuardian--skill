# HealthGuardian-Skill

個人健康守護者 - 一個基於 OpenClaw 架構的 AI 健康管理系統

## 專案概覽

HealthGuardian-Skill 是一個整合化的個人健康管理系統，利用 Claude Code 的 AI 能力實現：

- 自動記錄與追蹤每日健康指標
- 智能解析體檢報告與處方單
- 藥品管理與用藥提醒
- 健康趨勢分析與預警

## 系統架構

### 四大功能模組

| 模組名稱 | 功能描述 | 技術實現 |
|---------|---------|---------|
| **VitalsTracker** | 記錄每日血壓、血糖、心率、睡眠及運動情況 | SQLite 本地資料庫 + 自然語言解析 |
| **MedReportAnalyzer** | 解析體檢報告、處方單照片 | Claude Vision API + OCR |
| **MedReminder** | 藥品管理與用藥提醒 | 資料庫 + Cron Job 定時任務 |
| **HealthConsultant** | 綜合分析與趨勢預警 | 數據分析引擎 + 預警規則 |

## 專案結構

```
HealthGuardian-Skill/
├── db_manager.py           # 資料庫管理模組 (已完成)
├── vitals_tracker.py       # 生命指標追蹤器 (待開發)
├── med_report_analyzer.py # 體檢報告解析器 (待開發)
├── med_reminder.py         # 藥品提醒器 (待開發)
├── health_consultant.py    # 健康顧問 (待開發)
├── prompts/                # 提示詞模板目錄
│   └── ocr_template.txt    # OCR 識別提示詞
├── config/                 # 配置文件
│   └── thresholds.json     # 預警閾值配置
└── health_log.db           # SQLite 資料庫 (自動生成)
```

## 資料庫架構

### daily_metrics - 每日健康指標表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| date | TEXT | 日期 (YYYY-MM-DD) |
| systolic_bp | INTEGER | 收縮壓 (mmHg) |
| diastolic_bp | INTEGER | 舒張壓 (mmHg) |
| heart_rate | INTEGER | 心率 (bpm) |
| fasting_glucose | REAL | 空腹血糖 (mmol/L) |
| sleep_hours | REAL | 睡眠時數 |
| sleep_quality | INTEGER | 睡眠品質 (1-5) |
| steps | INTEGER | 步數 |
| notes | TEXT | 備註 |

### medical_records - 體檢報告異常項表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| report_date | TEXT | 報告日期 |
| report_type | TEXT | 報告類型 |
| item_name | TEXT | 檢查項目名稱 |
| value | TEXT | 數值 |
| unit | TEXT | 單位 |
| reference_range | TEXT | 參考範圍 |
| status | TEXT | 狀態 (正常/偏高/偏低) |
| severity | TEXT | 嚴重程度 |
| notes | TEXT | 備註 |

### medications - 藥品管理表

| 欄位 | 類型 | 說明 |
|------|------|------|
| id | INTEGER | 主鍵 |
| name | TEXT | 藥品名稱 |
| dosage | TEXT | 劑量規格 |
| frequency | TEXT | 服用頻率 |
| total_quantity | INTEGER | 總數量 |
| remaining_quantity | INTEGER | 剩餘數量 |
| expiry_date | TEXT | 有效期 |
| start_date | TEXT | 開始服用日期 |
| notes | TEXT | 備註 |

## 使用範例

### 基本使用

```python
from db_manager import DatabaseManager, DailyMetric
from datetime import datetime

# 初始化資料庫
db = DatabaseManager("health_log.db")

# 新增今日指標
today = datetime.now().strftime("%Y-%m-%d")
metric = DailyMetric(
    id=None,
    date=today,
    systolic_bp=135,
    diastolic_bp=85,
    heart_rate=78,
    fasting_glucose=6.2,
    sleep_hours=6.5,
    sleep_quality=3,
    steps=5000,
    notes="睡眠不足"
)
db.add_daily_metric(metric)

# 查詢最近 30 天趨勢
bp_trend = db.get_bp_trend(30)
print(f"最近血壓趨勢: {bp_trend}")

# 關閉連線
db.close()
```

### 使用 with 語句

```python
with DatabaseManager() as db:
    # 自動管理連線
    metrics = db.get_recent_metrics(7)
    for metric in metrics:
        print(f"{metric.date}: 血壓 {metric.systolic_bp}/{metric.diastolic_bp}")
```

## 開發進度

- [x] 第一階段：基礎設施與本地資料庫構建
  - [x] 設計資料庫 Schema
  - [x] 編寫 db_manager.py 封裝類

- [x] 第二階段：多模態解析能力開發
  - [x] 編寫提示詞模板（`prompts/ocr_template.txt`）
  - [x] 實現圖片預處理介面（`med_report_analyzer.py`）
  - [x] 建立預警閾值配置（`config/thresholds.json`）

- [ ] 第三階段：邏輯判斷與預警引擎
  - [ ] 設定閾值邏輯
  - [ ] 編寫健康週報生成邏輯

- [ ] 第四階段：語音化與外部集成
  - [ ] 集成 TTS
  - [ ] 配置 OpenClaw Action

## 預警閾值標準

| 指標 | 綠色 | 橙色 | 紅色 |
|------|------|------|------|
| 收縮壓 | <120 | 120-139 | ≥140 |
| 舒張壓 | <80 | 80-89 | ≥90 |
| 空腹血糖 | <5.6 | 5.6-6.9 | ≥7.0 |
| 心率 | 60-100 | - | <60 或 >100 |

## 授權

MIT License

# 情景记忆目录

此目录存放按年份归档的健康事件记录。

## 目录结构

```
episodic/
├── 2026/
│   └── ep-2026-04-29-001.json  # 示例事件文件
└── README.md
```

## 文件命名规则

`ep-YYYY-MM-DD-NNN.json`，其中 NNN 为当日序号。

## 事件文件格式

```json
{
  "id": "ep-YYYY-MM-DD-NNN",
  "timestamp": "YYYY-MM-DDTHH:MM:SS",
  "event_type": "指标异常|就诊|用药变化|症状发作",
  "situation": "发生了什么",
  "outcome": "结果",
  "lesson": "经验教训",
  "related_pattern": null,
  "confidence": 0.8
}
```

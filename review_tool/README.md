# 每日复盘分析工具

把每日复盘的结构化数据沉淀进 SQLite，再用 SQL 做周/月分析。

## 目录结构

```
每日复盘计划/
├── 每日复盘/            # 你每天把复盘 .md 文件丢这里
│   └── 2026-08-05.md
└── review_tool/         # 本项目
    ├── schema.sql       # 建表
    ├── config.py        # 路径与字段映射
    ├── db.py            # SQLite 读写
    ├── parse.py         # 解析 md -> 结构化 dict
    ├── ingest.py        # 入库脚本
    ├── analyze.py       # 周/月分析
    └── reviews.db       # 数据库 (自动生成)
```

## 使用流程

1. 每天写复盘，存成 `每日复盘/YYYY-MM-DD.md`，文件顶部放数据块：


   ```
   ```
2. 入库：`python ingest.py` （或 `python ingest.py 某个文件.md`）
3. 周分析：`python analyze.py week` 或 `python analyze.py week 32`
4. 月分析：`python analyze.py month` 或 `python analyze.py month 202608`

## 字段说明

| 列                                             | 含义                     |
| --------------------------------------------- | ---------------------- |
| date                                          | 日期主键                   |
| iso_week / month                              | 派生：ISO 周号 / 年月(202608) |
| training_day                                  | 是否训练日                  |
| sleep_h / sleep_quality                       | 睡眠时长(h) / 质量(0-100)    |
| supps_done / commute_done / breakfast_on_time | 补剂/通勤/早餐是否完成           |
| exercise_min                                  | 正式运动分钟                 |
| diet_kcal / meals_count                       | 饮食热量 / 三餐次数            |
| phone_h                                       | 手机屏幕时长(h)              |
| deepwork_h                                    | 深度工作(h)                |
| health/work/learn/life_score                  | 四维自评(1-10)             |
| system_score                                  | 派生：四维均值                |

## 设计要点

- SQLite 是唯一数据源；Excel 仅为可选导出（如需可另写脚本从 db 导出）。
- 解析兼容两种命名（如 `sleep_h` / `睡眠时长_h`），也兼容用户直接发的纯文本表头。
- 按 `date` 主键 upsert：同一天重复入库会覆盖，不会重复。
- 系统分四维度齐全才计算，缺失则留空。

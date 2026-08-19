# 每日复盘分析工具

把每日复盘的结构化数据沉淀进 SQLite，再用 SQL 做周/月分析。

## 目录结构

```
每日复盘计划/
├── 每日复盘/            # 你每天把复盘 .md 文件丢这里
│   ├── 复盘/2026-08/    # 自动生成/回填的复盘（按月份归档）
│   └── 历史源复盘/       # 旧源文件归档
└── review_tool/         # 本项目
    ├── schema.sql       # 建表 (含 CHECK 约束 + personal_tracks)
    ├── config.py        # 路径与字段映射 + 个人化配置(PROFILE/SCORE_THRESHOLDS)
    ├── db.py            # SQLite 读写
    ├── parse.py         # 解析 md -> 结构化 dict
    ├── score.py         # 四维评分自动生成
    ├── ingest.py        # 入库脚本
    ├── analyze.py       # 周/月分析
    ├── new_day.py       # 一键生成当天复盘文件
    ├── import_history.py# 语雀历史文件转换导入
    ├── reviews.db       # 你的数据库 (含个人数据)
    └── reviews.example.db # 空数据库模板 (新用户复制为 reviews.db)
```

## 使用流程

1. 生成当天文件：`python -m review_tool new-day`（或 `python -m review_tool new-day 2026-08-20` 指定日期），
   自动从模板复制并填好日期/星期，你只需改 `数据块` 里的数值和打卡勾选。
2. 入库：`python -m review_tool ingest` （或 `python -m review_tool ingest 某个文件.md`）
3. 周分析：`python -m review_tool week` 或 `python -m review_tool week 32`
4. 月分析：`python -m review_tool month` 或 `python -m review_tool month 202608`

模板数据块（```data 代码块）是**通用**数据入口，示例：

```data
日期: 2026-08-05
星期: 二
训练日: yes
睡眠时长_h: 6.42
睡眠质量: 84
入睡时间: 00:39
运动时长_min: 0
饮食热量_kcal: 1199
三餐情况: 早✓午✓晚✓
早餐按时: yes
手机屏幕_h: 10.9
健康分: 4
工作分: 6
学习分: 6
生活分: 5
一句话总结: ...
```

> 服药 / 护肤等个人定制项不在通用数据块中，由「日常打卡」勾选提取，单独落入 `personal_tracks` 表（不计入通用评分）。

## 字段说明

**`daily_reviews` 表（通用）**

| 列                                             | 含义                     |
| --------------------------------------------- | ---------------------- |
| date                                          | 日期主键                   |
| iso_week / month                              | 派生：ISO 周号 / 年月(202608) |
| training_day                                  | 是否训练日                  |
| sleep_h / sleep_quality                       | 睡眠时长(h) / 质量(0-100)    |
| commute_done / breakfast_on_time              | 通勤/早餐是否完成              |
| exercise_min                                  | 正式运动分钟                 |
| diet_kcal / meals_count                       | 饮食热量 / 三餐次数            |
| phone_h                                       | 手机屏幕时长(h)              |
| deepwork_h / learn_h / life_h                 | 深度工作 / 学习投入 / 生活投入 (h) |
| health/work/learn/life_score                  | 四维评分(1-10)：均可由系统按数据自动生成（完整规则见根目录 README.md） |
| system_score                                  | 派生：四维均值                |

**`personal_tracks` 表（个人定制，不计入通用评分）**

| 列                          | 含义                                       |
| -------------------------- | ---------------------------------------- |
| date / category / item (PK) | 日期 / 类别(服药·护肤·自定义) / 具体项           |
| done                       | 是否完成 (0/1)                              |
| note                       | 备注                                       |

## 设计要点

- SQLite 是唯一数据源；Excel 仅为可选导出（如需可另写脚本从 db 导出）。
- 解析兼容三种格式：```data 代码块 / markdown 注释块 / 用户直接发的纯文本表头。
- 按 `date` 主键 upsert：同一天重复入库会覆盖，不会重复。
- 系统分四维度齐全才计算，缺失则留空。
- 自动评分：ingest 时若四维分缺失则自动生成——健康分基于睡眠/运动/饮食/屏幕等客观指标规则加权计算（补剂/护肤等个人定制项不计入，见 personal_tracks 表），工作分基于 `深度工作_h`、学习分基于 `学习投入_h`、生活分基于 `生活投入_h` 分档计算；只补缺失值，不覆盖手填。完整阈值见根目录 README.md 的「评分规则」一节，阈值与权重定义于 `config.SCORE_THRESHOLDS`。
- 数据块字段：四维分 1-10、睡眠质量 0-100、布尔 0/1、数值非负，均有 CHECK 约束拦截脏数据。
- 入睡时间 `bedtime` 存距 00:00 分钟数（23:47 → 1427），便于聚合分析。
- 个人化配置：`config.PROFILE`（补剂/护肤/作息）与 `config.SCORE_THRESHOLDS`（评分阈值）为可配置层，小伙伴改这两处即可适配自己。

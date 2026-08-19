# DailyLumen · 每日复盘系统

把每天的结构化复盘沉淀进 **SQLite 单一数据源**，再用脚本做周 / 月分析。
复盘模板、数据解析、四维评分自动化、入库与分析全部基于 Python 标准库（零依赖）。

---

## 目录结构

```
每日复盘计划/                         # 项目根 (仓库名 DailyLumen)
├── README.md                         # 本文件：项目说明 + 评分规则
├── pyproject.toml                    # 项目元数据 + pytest 配置（零依赖）
├── requirements.txt                  # 依赖说明（运行时零依赖）
├── 每日复盘模板.md                    # 每天复盘的模板（一键生成时复制它）
├── 每日复盘/                         # 你每天把复盘 .md 文件丢这里（入库数据源）
│   ├── 复盘/2026-08/                # 自动生成/回填的复盘（按月份归档）
│   │   ├── 2026-08-17.md
│   │   └── ...
│   ├── 历史源复盘/                   # 旧源文件归档（不参与新流程）
│   └── 收件箱/                       # 晨间收集投放截图/简报的目录
├── tests/                            # 测试套件（标准库 unittest，零依赖）
│   ├── test_parse.py
│   ├── test_score.py
│   ├── test_db.py
│   └── test_ingest.py
└── review_tool/                      # 解析 / 评分 / 入库 / 分析（标准 Python 包）
    ├── __init__.py                   # 包公共 API 导出
    ├── __main__.py                   # 统一命令行入口 (python -m review_tool)
    ├── config.py                     # 路径常量 + 个人化配置(PROFILE/SCORE_THRESHOLDS)
    ├── db.py                         # SQLite 读写（建表 / upsert / 查询）
    ├── parse.py                      # 解析 md -> 结构化 dict（兼容三种格式）
    ├── score.py                      # 四维评分自动生成 ★
    ├── ingest.py                     # 入库（按 date 主键 upsert）
    ├── analyze.py                    # 周 / 月分析
    ├── new_day.py                    # 一键生成当天复盘文件
    ├── import_history.py             # 语雀历史文件转换导入
    ├── schema.sql                    # 建表（含 CHECK 约束 + personal_tracks）
    ├── reviews.db                    # 你的数据库（单一数据源，含个人数据）
    └── reviews.example.db            # 空数据库模板（新用户复制为 reviews.db 即可）
```

---

## 使用流程

所有命令统一通过包入口 `python -m review_tool` 运行（项目已改造为标准 Python 包，相对 import，可在任意目录执行）。

1. **生成当天文件**
   ```bash
   python -m review_tool new-day            # 默认今天
   python -m review_tool new-day 2026-08-20 # 指定日期
   ```
   自动从模板复制并填好日期 / 星期，你只需改 `附录 · 系统数据` 里的数值和打卡勾选。
2. **入库**
   ```bash
   python -m review_tool ingest            # 入库「每日复盘/」全部文件
   python -m review_tool ingest 某个文件.md # 入库指定文件
   ```
3. **周分析**
   ```bash
   python -m review_tool week        # 所有周
   python -m review_tool week 32     # 指定 ISO 周
   ```
4. **月分析**
   ```bash
   python -m review_tool month        # 本月（最近一个月）
   python -m review_tool month 202608 # 指定年月
   ```
5. **历史语雀文件导入**
   ```bash
   python -m review_tool import-history            # 转换并写入「每日复盘/」
   python -m review_tool import-history --check    # 仅预览解析结果
   python -m review_tool import-history --src DIR  # 指定来源目录（也可用环境变量 DAILYLUMEN_HISTORY_SRC）
   ```

## 运行测试

测试基于 Python 标准库 `unittest`，**零额外依赖**：

```bash
python -m unittest discover -s tests -t .
```

（若偏好 pytest，安装后直接 `pytest` 即可，已在 `pyproject.toml` 配置 `pythonpath` 与 `testpaths`。）

覆盖：解析三种格式 / bedtime 分钟化 / 三餐计数、健康分加权与跨午夜、工作/学习/生活分档、CHECK 约束拦截、upsert 幂等、入库端到端。

### 数据块（通用数据入口）

复盘文件末尾的 ```` ```data ```` 代码块是**通用**数据入口，字段示例：

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
深度工作_h: 0
学习投入_h: 1.5
生活投入_h: 2.0
健康分:
工作分:
学习分:
生活分:
一句话总结: ...
```

解析兼容三种格式：` ```data ` 代码块 / HTML 注释块 / 用户直接发的纯文本表头；按 `date` 主键 upsert，同一天重复入库会覆盖、不会重复。

> **个人定制项（服药 / 护肤）不在此数据块中**：它们由「一、日常打卡」勾选提取，单独落入 `personal_tracks` 表，不计入通用评分。

---

## 📊 评分规则（核心）

四维评分：**健康 / 工作 / 学习 / 生活**，各自 1–10 分；**系统分 = 四维均值**（四维齐全才计算，保留 2 位小数）。

入库时（`ingest.py`）若某维分缺失则自动生成——**只补 `None` 的，绝不覆盖手填值**。
旧数据（如 2026-08-05 的手填分 4/6/6/5）会原样保留。

### 1. 健康分（规则化加权，基于客观健康子指标）

健康分由各子指标加权求和得到，权重和为 1.0。**任意子指标缺失则跳过该项，剩余权重重新归一化**；最终结果 clamp 到整数 1–10。

| 子指标 | 权重 | 评分标准 |
| --- | --- | --- |
| 睡眠时长 | 0.18 | ≥8h → **10**（满分）｜≥7h → 8｜≥6.5h → 6｜≥6h → 4｜<6h → 2 |
| 睡眠质量 | 0.12 | 0–100 线性映射到 0–10（quality ÷ 10） |
| 入睡时间 | 0.15 | 00:00–05:00（熬夜到凌晨）→ 3｜≤22:30 → **10**｜22:30–23:30 → 8｜23:30–23:59 → 5 |
| 运动 | 0.25 | **训练日**：≥30min → 10｜≥10min → 6｜否则 2　**非训练日**：≥20min → 8｜否则 6 |
| 饮食热量 | 0.10 | 1200–2200 kcal → 8｜1000–1200 或 2200–2600（边界）→ 5｜其余 → 3 |
| 手机屏幕 | 0.15 | ≤4h → **10**｜≤6h → 8｜≤8h → 6｜≤10h → 4｜>10h → 2 |

> 权重和为 0.95（服药依从已移出通用评分），缺失子项时剩余权重自动归一化。服药 / 护肤等个人定制项不计入通用健康分，单独统计于 `personal_tracks` 表（定义见 `config.PROFILE`）。

> 入睡时间 `bedtime` 存「距 00:00 的分钟数」(23:47 → 1427，00:39 → 39)。
> 跨午夜的凌晨时段（≤300 分钟）判断优先于当晚时段，避免命中 ≤22:30 拿满分。

### 2. 工作分（基于深度工作时长 `deepwork_h`）

| 深度工作_h | 工作分 |
| --- | --- |
| ≥ 6h | 9 |
| ≥ 4h | 7 |
| ≥ 2h | 5 |
| < 2h | 3 |

### 3. 学习分（基于学习投入时长 `learn_h`）

| 学习投入_h | 学习分 |
| --- | --- |
| ≥ 3h | 9 |
| ≥ 2h | 7 |
| ≥ 1h | 5 |
| < 1h | 3 |

### 4. 生活分（基于生活投入时长 `life_h`）

规则与学习分完全相同：

| 生活投入_h | 生活分 |
| --- | --- |
| ≥ 3h | 9 |
| ≥ 2h | 7 |
| ≥ 1h | 5 |
| < 1h | 3 |

### 5. 系统分

```
系统分 = round((健康分 + 工作分 + 学习分 + 生活分) / 4, 2)
```

四维中任一缺失则不计算，留空。

---

## 数据库字段速查

**`daily_reviews` 表（通用）**

| 列 | 含义 |
| --- | --- |
| `date` (PK) | 日期主键 `YYYY-MM-DD` |
| `iso_week` / `month` | 派生：ISO 周号 / 年月 (202608) |
| `training_day` | 是否训练日 (0/1) |
| `sleep_h` / `sleep_quality` | 睡眠时长(h) / 质量(0–100) |
| `bedtime` | 入睡时间：距 00:00 分钟数 |
| `commute_done` / `breakfast_on_time` | 通勤 / 早餐是否完成 (0/1) |
| `exercise_min` | 正式运动分钟 |
| `diet_kcal` / `meals_count` | 饮食热量 / 三餐次数 |
| `phone_h` | 手机屏幕时长(h) |
| `deepwork_h` / `learn_h` / `life_h` | 深度工作 / 学习投入 / 生活投入 (h) |
| `health_score` / `work_score` / `learn_score` / `life_score` | 四维评分 (1–10) |
| `system_score` | 派生：四维均值 |
| `summary` / `raw_path` / `ingested_at` | 一句话总结 / 来源文件 / 入库时间 |

**`personal_tracks` 表（个人定制，不计入通用评分）**

| 列 | 含义 |
| --- | --- |
| `date` + `category` + `item` (PK) | 日期 / 类别(服药·护肤·自定义) / 具体项 |
| `done` | 是否完成 (0/1) |
| `note` | 备注 |

完整建表语句与 CHECK 约束见 `review_tool/schema.sql`。

---

## 个人化配置（可配置层）

本项目对「个人差异」做了显式抽象，小伙伴拿到后**只需改 `review_tool/config.py` 两处**，无需碰模板与代码：

- **`PROFILE`**：补剂方案（早/午/晚）、护肤项、早餐作息窗口。这些项由入库脚本从「日常打卡」勾选提取，落入 `personal_tracks` 表单独统计。
- **`SCORE_THRESHOLDS`**：四维评分的阈值与权重（睡眠/入睡/运动/饮食/屏幕/深度工作/学习/生活）。默认值 = 当前用户的评分偏好，可自由调整。

---

## 设计要点

- **SQLite 是唯一数据源**：通用结构化字段落在 `daily_reviews` 表；补剂 / 护肤等**个人定制项**单独落在 `personal_tracks` 表，不计入通用评分。
- **个人化可配置**：补剂方案 / 护肤 / 作息窗口定义于 `config.PROFILE`，评分阈值与权重定义于 `config.SCORE_THRESHOLDS`；改这两处即可适配不同用户。
- **解析向后兼容**：旧格式（注释块 / 纯文本表头）都能被新解析器识别并入库。
- **防脏数据**：四维 1–10、质量 0–100、布尔 0/1、数值非负，均有 CHECK 约束拦截。
- **评分可解释**：健康分为客观子指标加权，工作 / 学习 / 生活分基于时长分档，规则全部透明（见上）。
- **零依赖**：纯 Python 标准库，`requirements.txt` 为空也能跑。

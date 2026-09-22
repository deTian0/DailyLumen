# DailyLumen · 每日复盘系统

把每天的结构化复盘沉淀进 **SQLite 单一数据源**，再用脚本做周 / 月分析、体检与导出。  
复盘模板、数据解析、四维评分自动化、入库、分析与体检全部基于 Python 标准库（**零依赖**）。

> 当前版本 **1.4.3**（skills 归类合并 + 方法资产入库 + 人格归位）
> · 规则与变更历史见 [`docs/设计说明.md`](docs/设计说明.md)｜包级模块速查见 [`review_tool/README.md`](review_tool/README.md)

---


## 目录结构

```
每日复盘计划/                         # 项目根 (仓库名 DailyLumen)
├── README.md                         # 本文件：项目说明 + 评分规则
├── review_tool/README.md             # 包级速查：模块地图 + CLI + 数据安全约定
├── pyproject.toml                    # 项目元数据 + pytest / ruff 配置（运行时零依赖）
├── requirements.txt                  # 依赖说明（运行时零依赖）
├── 每日复盘模板.md                    # 每天复盘的模板（一键生成时复制它）
├── 每日复盘/                         # 数据源根目录
│   ├── 复盘/2026-08/                # 标准复盘（按月份归档，ingest 扫描这里）
│   ├── 历史源复盘/                   # 旧格式归档（不参与 ingest，需先转换）
│   └── 收件箱/                       # 晨间收集投放截图/简报的目录（不参与 ingest）
├── docs/                             # 设计说明与口径（评分 / 统计 / 字段 / 变更日志）
├── tests/                            # 测试套件（标准库 unittest，零依赖，288 项）
├── .github/workflows/ci.yml          # CI：多 Python 版本测试 + ruff 检查
├── .workbuddy/                       # 工作区配置（不参与运行；除 skills/ 外均不入 git）
│   ├── skills/                       # 项目级 skill（**已入 git**，方法资产跟代码一起版本化）
│   │   └── doc-corpus-normalize/     # 文档批量标准化 SOP（可证明无损）
│   ├── memory/                       # 会话日志 + 项目长期约定 MEMORY.md
│   └── backup/                       # 迁移备份与一次性脚本（不入 git）
└── review_tool/                      # 解析 / 评分 / 入库 / 分析 / 体检（标准 Python 包）
    ├── __init__.py                   # 包公共 API 导出
    ├── __main__.py                   # 统一命令行入口 (python -m review_tool)
    ├── config.py                     # 路径 + 可配置层(PROFILE/PERSONAL_ITEMS/SCORE_THRESHOLDS/BODYWEIGHT_MOVES)
    ├── util.py                       # 时间与数值转换、slug 生成
    ├── tracks.py                     # 打卡项归一化（自由文本 -> 规范 ID）★
    ├── bodyweight.py                 # 徒手训练折算（描述动作 -> 运动时长）★
    ├── db.py                         # SQLite 读写 + 带版本的增量迁移
    ├── parse.py                      # 解析 md -> 结构化 dict（兼容三种格式）
    ├── score.py                      # 四维评分自动生成 ★
    ├── ingest.py                     # 入库（按 date 主键 upsert，默认不擦数据）
    ├── analyze.py                    # 周 / 月分析
    ├── new_day.py                    # 一键生成当天复盘文件
    ├── ai_review.py                  # 「七、AI 评价与建议」上下文构建器 ★
    ├── import_history.py             # 语雀历史文件转换导入
    ├── doctor.py                     # 数据体检（对账 / 完整度 / 新鲜度 / 分数一致性 / 打卡对账 / 熔断）★
    ├── fuse.py                       # 熔断检测（连续走低 + 相对基线偏离）★
    ├── sync_docs.py                  # 把库里的分数回写到复盘 md（数据块 + 六章）★
    ├── recompute.py                  # 按当前规则重算库中四维 / 系统分 ★
    ├── export.py                     # CSV / JSON 导出
    ├── schema.sql                    # 建表（含 CHECK 约束）
    ├── reviews.db                    # 你的数据库（单一数据源，含个人数据）
    └── reviews.example.db            # 空数据库模板（新用户复制为 reviews.db 即可）
```

---


## 使用流程

所有命令统一通过包入口 `python -m review_tool` 运行，可在任意目录执行。  
加 `-h` 查看任意子命令的参数。

| 命令                                                   | 用途                                     |
| ---------------------------------------------------- | -------------------------------------- |
| `new-day [YYYY-MM-DD] [--force]`                     | 按模板生成当天文件 → `复盘/YYYY-MM/`              |
| `ingest [路径.md] [--overwrite] [--prune-tracks]`      | 解析并入库（默认只补空值，不擦已有数据；`--prune-tracks` 顺带清陈旧打卡） |
| `week [ISO周] [--json]` / `month [YYYYMM] [--json]`   | 周 / 月分析（`--json` 输出结构化结果，便于接自动化）      |
| `ai-context [YYYY-MM-DD]`                            | 输出「七、AI 评价与建议」的确定性上下文                  |
| `import-history [--check] [--src DIR]`               | 语雀历史文件转换为标准格式                          |
| `doctor`                                             | 数据体检：对账 / 完整度 / 新鲜度 / 分数一致性 / 打卡对账 / 归一化 / 熔断 |
| `fuse`                                               | 熔断检测：单维度持续走低 + 相对基线偏离                  |
| `sync-docs [--check]`                                | 把库里的四维分回写到复盘 md（数据块 + 六章表格）            |
| `recompute-scores [--apply]`                         | 按当前规则重算库中四维 / 系统分（默认只试算）               |
| `export [--format csv\|json] [--out DIR] [--stdout]` | 导出结构化数据                                |
| `version`                                            | 打印版本号                                  |

典型日常：

```bash
python -m review_tool new-day            # 1. 生成当天文件
                                         # 2. 打开填数值与勾选
python -m review_tool ingest             # 3. 入库（自动补四维评分）
python -m review_tool ai-context         # 4. 拿事实依据写「七、AI 评价与建议」
python -m review_tool ingest             # 5. 再入库一次兜底
python -m review_tool doctor             # 6. 体检：数据齐不齐、有没有该补的
```

### ⚠️ 入库的两种模式

`ingest` 默认是**保护模式**：源文件里为空的字段**不会**擦掉库里已有的值  
（防止「重跑一次 ingest 把已经攒下的数据清空」）。

确需用源文件真正清空某字段时，显式加 `--overwrite`：

```bash
python -m review_tool ingest --overwrite
```

### 运行测试

```bash
python -m unittest discover -s tests -t .      # 200 项，零依赖
```

覆盖：解析三种格式 / 打卡归一化 / 徒手训练折算 / 迁移幂等与表重建自愈 /  
upsert 防覆盖 / 训练日二态口径 / 评分边界 / 模板生成 / 体检 / 导出 /  
配置自洽 / 版本一致性。

---

## 数据块（通用数据入口）

复盘文件末尾的 ` ```data ` 代码块是**通用**数据入口，字段示例：

```data
日期: 2026-08-05
星期: 二
训练日: yes
睡眠时长_h: 6.42
睡眠质量: 84
入睡时间: 00:39
运动时长_min: 0
饮食热量_kcal: 1199
碳水_g: 150
脂肪_g: 40
蛋白质_g: 55
三餐情况: 早✓午✓晚✗
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

解析兼容三种格式：` ```data ` 代码块 / HTML 注释块 / 用户直接发的纯文本表头；  
按 `date` 主键 upsert，同一天重复入库会覆盖（保护模式下只补空）。

> **个人定制项（补剂 / 护肤）不在此数据块中**：它们由「一、日常打卡」勾选提取，  
> 归一化后落入 `personal_tracks` 表，不计入通用评分。详见下文「个人打卡归一化」。

---

## 🔖 个人打卡归一化（v1.3.0 新增）

**问题**：打卡项手写文本天然不稳定。改造前实测 244 条打卡记录里出现 **16 种文本形态**，  
实际只对应 6 个规范项——同一个 CoQ10 可能写成「CoQ10 ×1」「晨间-CoQ10 ×1 ＋ Exia 早3」  
「CoQ10 ×1 ＋ Exia 早3」…… 导致**依从率根本无法聚合**。

**方案**：打卡项定义收敛为 `config.PERSONAL_ITEMS` 单一来源，解析时归一化到规范 ID：

| 输入文本                           | 归一化结果                                 |
| ------------------------------ | ------------------------------------- |
| 「晨间」小节 + `CoQ10 ×1 ＋ Exia 早3`  | `coq10@morning`, `exia_am@morning`    |
| 「晚间」小节 + `Exia 晚3 ＋ Move Free` | `exia_pm@evening`, `movefree@evening` |
| 无小节 + `Move Free 红色 ×1`        | `movefree`（时段未知）                      |
| 任意位置 + `护肤`                    | `skincare`                            |

- `item_key` 规范项 ID（不含时段）—— **按它聚合依从率**
- `track_key` 规范项 ID + 时段后缀（`@morning` / `@noon` / `@evening`），时段未知则无后缀
- 未收录的新写法不会被丢弃：生成稳定的 `other:<slug>`，同样可聚合；  
  `doctor` 会把它列出来提示你补 alias

时段规则由 `PERSONAL_ITEMS` 的 `per_slot` 控制：  
`per_slot=True`（如 Move Free 午/晚都可能吃）跟随小节标题；`False`（如护肤）固定不分时段。

改造后实测：**16 种写法 → 6 个规范项，0 条未收敛**，依从率首次可算。

---


---

## 📐 设计与口径（已独立成册）

评分规则、口径定义、字段速查与变更日志已移到 **[`docs/设计说明.md`](docs/设计说明.md)**，
本文件只保留「怎么用」。涉及以下主题时请查设计说明：

| 想了解 | 去哪里 |
| --- | --- |
| 四维评分怎么算、档位阈值、熔断规则 | [设计说明 · 评分规则](docs/设计说明.md#-评分规则核心) |
| 分数的单一权威（库为准 / md 由库渲染） | [设计说明 · 分数的单一权威](docs/设计说明.md#-分数的单一权威v140) |
| 训练日达标、运动折算等统计口径 | [设计说明 · 统计口径](docs/设计说明.md#-统计口径v130v132-三轮收口) |
| 数据库字段含义 | [设计说明 · 数据库字段速查](docs/设计说明.md#数据库字段速查) |
| 版本变更历史 | [设计说明 · 变更日志](docs/设计说明.md#变更日志) |

## 🩺 数据体检（`doctor`）

一次性回答「数据还准不准、全不全、新不新」：

```bash
python -m review_tool doctor
```

| 检查项        | 说明                                     |
| ---------- | -------------------------------------- |
| 数据库        | schema 版本 / 记录数 / 完整性检查                |
| 新鲜度        | 最新复盘距今多少天，超过 1 天即提示补录                  |
| 文件 ↔ 数据库对账 | 双向差集：哪些 md 没入库、哪些库中记录找不到源文件            |
| 旧格式归档      | 哪些天的数据源只存在于「历史源复盘」，建议先转换               |
| 数据完整度      | 核心字段缺失统计                               |
| 打卡归一化      | 是否还有未收敛到规范项的 `other:*` 记录              |
| 训练日口径      | 记录值与日期约定不一致的天数（提示性）                    |
| 分数一致性      | 库中四维 / 系统分 vs「按字段重算」的结果（v1.4.1；提示性，不拦） |
| 打卡对账       | 库中打卡行能否在源 md 找到对应勾选（v1.4.2；提示性，不拦）     |
| 熔断检测       | 单维度连续低分 + 相对基线漂移（v1.4.0；提示性，不拦）        |

退出码：健康 = 0，有待处理项 = 1（便于接入自动化）。

## 📤 导出（`export`）

```bash
python -m review_tool export                    # 3 个 CSV 到 exports/（utf-8-sig，Excel 直开）
python -m review_tool export --format json      # 单个 JSON
python -m review_tool export --stdout           # 打印到终端
```

导出三份数据：`daily_reviews`（每日通用字段）、`personal_tracks`（打卡明细）、  
`adherence`（**按规范项聚合的依从率**）。

---

## 🤖 AI 评价与建议（第七章）

每日复盘模板固定包含 `## 七、AI 评价与建议`，由晨间收集自动化在回填数据后生成：

- **评价**：2–3 条，含「做得好」与「需留意」，必须引用当日与近 7 日的实际数字。
- **建议**：2–4 条可执行动作，带具体时间锚点或目标值。

撰写前先运行上下文构建器拿事实依据：

```bash
python -m review_tool ai-context 2026-09-15
```

输出三块内容（**全部来自读库与规则判定，不含模型生成**）：

1. **当日事实**：睡眠/饮食（含三大营养素）/屏幕/深度工作/学习/生活/四维分。
2. **近 7 日均值**：系统与四维、睡眠/屏幕/深度工作/饮食、宏量日均。
3. **规则命中的关注点**：按 `config.SCORE_THRESHOLDS` 阈值与  
   `config.PROFILE["macro_targets"]` 目标逐条判定。

关注点规则（均为客观陈述，不下结论）：

| 类别 | 触发条件                                              |
| -- | ------------------------------------------------- |
| 睡眠 | 时长 < 7h｜质量 < 80｜入睡落在熬夜档（00:00–06:00）或晚睡档（>23:30）  |
| 运动 | 训练日未记录（按口径记 0，v1.3.2：没填即没练）｜训练日运动 0 分钟            |
| 饮食 | kcal 出 1200–2200 区间；碳水/脂肪/蛋白低于 `macro_targets` 目标 |
| 屏幕 | > 10h                                             |
| 四维 | 工作/学习/生活分 ≤3（最低档）                                 |
| 趋势 | 连续 ≥3 天出现同一问题（入睡晚 / 学习分 ≤3 / 屏幕 >10h）             |

> **文案里的时间点也是从配置算出来的**：例如「未在 23:30 前」取自  
> `SCORE_THRESHOLDS["bedtime"]["ok_max"]`，改阈值文案会跟着变，不会出现  
> 「阈值改了、文案还在说老数字」。
>
> 该章节为**叙事文本**，不入 `daily_reviews` 表、不参与评分；评分仍由客观规则决定。

---


## 个人化配置（可配置层）

本项目对「个人差异」做了显式抽象，小伙伴拿到后**只需改 `review_tool/config.py` 四处**，  
无需碰模板与代码：

- **`PROFILE`**：作息窗口、三大营养素每日目标（`macro_targets`）、  
  训练日约定（`training_weekdays`，0=周一）。
- **`PERSONAL_ITEMS`**：个人打卡项定义（补剂 / 护肤 / 自定义），  
  每项含 `key` / `slot` / `per_slot` / `label` / `aliases`。  
  **这是解析与归一化的单一来源**，改这里即可适配自己的打卡方案。
- **`SCORE_THRESHOLDS`**：四维评分阈值与权重。默认值 = 当前用户的评分偏好；  
  同时驱动「AI 评价与建议」的关注点规则与文案。
- **`BODYWEIGHT_MOVES` / `BODYWEIGHT_RULES`**：徒手训练折算。每项含  
  `aliases` / `per_minute` / `set_rest_sec` / `default_reps`；  
  规则含单日上下限与次数合理性上限。**默认只启用俯卧撑**，  
  其他动作按同样结构追加一行即可。

`tests/test_config.py` 会校验配置自洽性（权重与实现对应、alias 不互相抢匹配、  
阈值单调性、版本一致性），改错配置测试会直接报出来。

---

## 工作区配置（`.workbuddy/`）

`.workbuddy/` 存放工作区级配置与记忆，**不参与程序运行**：

- **`skills/`**（**已入 git**）：项目级 skill，属**方法资产** —— 跟代码一起版本化、打 tag。
  当前含 `doc-corpus-normalize`（批量文档标准化 SOP，保证解析 / 入库可证明无损）。
  `.gitignore` 用 `.workbuddy/*` + `!.workbuddy/skills/` 开白名单；**注意必须写成
  `.workbuddy/*`**，写成 `.workbuddy/` 会连目录一起排除，白名单会静默失效。
- **`memory/`**（不入 git）：会话执行日志（按日期）+ 项目长期约定（`MEMORY.md`，
  如评分口径、迁移规约、工程约定）。开工前先读、做完后写回，保证跨会话连续性。
- **`backup/`**（不入 git）：数据库迁移前备份、一次性脚本与 `archived/` 归档。

**人格与跨项目 SOP 不在本仓库**：
助手人格与协作准则已归到用户级记忆 `~/.workbuddy/MEMORY.md` 的「协作准则」段
（每会话无条件注入，机制上保证 always-on）；跨项目通用 SOP（`sqlite-safe-migration`
含「假装自己是 CI」自检、`nmpa-cosmetic-record`）在用户级 `~/.workbuddy/skills/`。
用户级资产的保管**不属本仓库职责**，本仓库只保证项目级 skill 随代码入库。

---


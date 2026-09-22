# review_tool — 包级说明（速查）

> 每日复盘数据管道：`md → 解析 → 评分 → SQLite → 周/月分析 / 体检 / 导出`。
> 本文件是**包内速查**；使用说明见仓库根目录 [`README.md`](../README.md)，
> 完整规则（评分口径、统计口径、字段含义、设计要点、变更日志）见 [`docs/设计说明.md`](../docs/设计说明.md)。

## 分层架构

依赖只能自上而下，由 `tests/test_architecture.py` 用 ast 强制（破坏分层 → CI 红）：

```
reports   ->  pipeline  ->  storage  ->  core
(读库产出)    (md <-> 库)   (SQLite)   (纯规则)
```

- **`core/` 领域层**：零 I/O —— 禁止 `sqlite3` / `os` / `pathlib` 等，可脱离库与文件系统单独测试。
- **`storage/` 持久化层**：`import sqlite3` **只允许出现在这里**，SQLite 是唯一出入口。
- **`pipeline/` 数据流转层**：复盘 md ↔ 库（解析 / 入库 / 回写 / 转换 / 生成 / 导出）。
- **`reports/` 产出层**：读库生成面向人的结果（分析 / 体检 / 熔断 / AI 上下文 / 分数维护）。
- 包根的 **`config.py`** 是可配置层（**唯一要改的文件**）；**`__main__.py`** 是纯路由。

## 模块地图

### 包根
| 模块 | 职责 |
| --- | --- |
| `config.py` | 路径常量（全靠 `__file__` 推导，无硬编码绝对路径）+ 可配置层：`PROFILE` / `PERSONAL_ITEMS` / `SCORE_THRESHOLDS` / `BODYWEIGHT_MOVES` |
| `schema.sql` | 建表语句（含 CHECK 约束），与 `reviews*.db` 同在包根 |
| `__init__.py` | 包公共 API（对外唯一契约，`__all__`） |
| `__main__.py` | **纯路由**：只派发子命令，参数由各模块自己解析（单一来源，杜绝静默丢参） |

### core/ —— 领域层（零 I/O）
| 模块 | 职责 |
| --- | --- |
| `util.py` | 时间与数值转换（`clock_to_minutes` / `to_int` / `to_float` / `slugify`） |
| `tracks.py` | 打卡项归一化：自由文本 → 规范 `track_key` / `item_key` |
| `bodyweight.py` | 徒手训练折算：描述里的动作 → 运动分钟（段落门控 + 上下限） |
| `score.py` | 四维评分规则（健康加权子项；工作/学习/生活时长分档） |

### storage/ —— 持久化层
| 模块 | 职责 |
| --- | --- |
| `db.py` | SQLite 读写 + `PRAGMA user_version` 增量迁移（含表重建的原子化流程）+ `prune_personal_tracks` 打卡对账 |

### pipeline/ —— 数据流转层（md ↔ 库）
| 模块 | 职责 |
| --- | --- |
| `parse.py` | md → 结构化 dict（兼容 ```` ```data ```` 块 / HTML 注释块 / 纯文本散落三种格式）；`has_tracks_section` 供打卡对账判断权威性 |
| `ingest.py` | 扫描 / 解析 / 折算 / 补零 / 评分 / 入库 |
| `sync_docs.py` | 把库里的四维分回写到复盘 md（附录数据块 + 「六、四维评分」表） |
| `import_history.py` | 语雀历史复盘 → 标准格式转换（输出到 `每日复盘/复盘/YYYY-MM/`） |
| `new_day.py` | 按模板生成当天复盘文件（写入 `每日复盘/复盘/YYYY-MM/`） |
| `export.py` | 导出 CSV / JSON（含依从率表） |

### reports/ —— 产出层
| 模块 | 职责 |
| --- | --- |
| `analyze.py` | 周 / 月聚合报告（`collect()` 取数 + `render_summary()` 排版，`--json` 复用同一份数据） |
| `doctor.py` | 数据体检：schema / 完整性 / 新鲜度 / md↔DB 对账 / 分数一致性 / 打卡对账 / 归一化 / 来源分布 / 熔断 |
| `fuse.py` | 熔断检测：单维度连续走低（绝对）+ 近 7 日 vs 前 28 日均值漂移（相对） |
| `ai_review.py` | 「AI 评价与建议」的确定性上下文（当日事实 + 7 日均值 + 命中规则） |
| `recompute.py` | 按当前规则重算库中四维 / 系统分（默认只试算，`--apply` 落库） |

## 命令行速查

```bash
python -m review_tool version                       # 版本
python -m review_tool new-day [YYYY-MM-DD] [--force]   # 生成当天文件 → 复盘/YYYY-MM/
python -m review_tool ingest [文件] [--overwrite] [--prune-tracks]   # 入库 + 可选打卡对账
python -m review_tool week [周号] [--json]             # 周报（省略 = 全部周）
python -m review_tool month [YYYYMM] [--json]          # 月报（省略 = 最近一个月）
python -m review_tool ai-context YYYY-MM-DD            # AI 上下文（当日 + 7 日趋势 + 关注点）
python -m review_tool import-history [--check] [--src 目录]   # 旧格式转换（--check 仅预览）
python -m review_tool doctor                           # 数据体检（exit≠0 表示有问题）
python -m review_tool fuse                             # 熔断检测（有绝对熔断时 exit=1）
python -m review_tool sync-docs [--check]              # 库中分数回写到 md（--check 仅报告）
python -m review_tool recompute-scores [--apply]       # 按规则重算四维/系统分（默认试算）
python -m review_tool export [--format csv|json] [--out 目录] [--stdout]
```

## 目录约定

```
每日复盘/
├── 复盘/YYYY-MM/     # 标准复盘源（ingest 只扫这里）——日复盘 + 周/月总结
├── 收件箱/           # 晨间素材，不参与 ingest（README/下划线前缀文件不计为待处理素材）
└── 历史源复盘/        # 旧格式源归档，不参与 ingest（需先 import-history 转换）
```

## 数据与安全

- `reviews.db` 是**唯一数据源**（含个人数据，勿提交）；`reviews.example.db` 是空库模板
  （与当前 schema 同版，见 `tests/test_example_db.py` 守卫）。
- **分数单一权威（v1.4.0 起）**：库为准、md 由 `sync-docs` 渲染。改评分规则后跑
  `recompute-scores --apply && sync-docs` 全库统一；`doctor` 的 `[分数一致性]` 段
  会点名「库值与字段重算不符」的行。upsert 仍用 `COALESCE`，防止空值刷掉已有数据。
- 改 schema 必须走迁移流程：**备份 → 副本验证 → 快照逐列 diff → 落真库**
  （流程与零依赖比对脚本见 `~/.workbuddy/skills/sqlite-safe-migration`）。
- 迁移完毕后跑 `doctor`：`md↔DB` 对账为 0、结论「数据健康」才算通过。
- **打卡对账**：`upsert_personal_track` 只增不删，源文本规范 ID 变化会留下陈旧键
  （同一剂量被重复计入依从率）。`doctor` 的 `[打卡对账]` 会报出来，
  清理用 `ingest --prune-tracks`（默认关闭；仅当打卡章节确实解析到才删）。

## 测试与代码风格

```bash
python -m unittest discover -s tests -t .   # 293 项，标准库零依赖
ruff check .                                # 静态检查（CI 同款）
```

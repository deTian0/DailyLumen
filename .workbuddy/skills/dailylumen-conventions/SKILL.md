---
name: dailylumen-conventions
description: DailyLumen 个人每日复盘系统的项目总纲 —— 范围边界、权威归属（分数归库 / 打卡归文）、四维评分与熔断口径、运动时长折算、文档模板规约、schema 迁移流程、CI 阻塞与版本节奏、换机迁移。在本仓库改代码 / 改文档 / 动数据库 / 发版本 / 迁移之前加载。触发词：DailyLumen、复盘系统、评分口径、改评分规则、熔断、运动折算、打卡对账、schema 迁移、换机迁移、周报月报口径。
agent_created: true
---

# DailyLumen 项目口径与工程约定

> 本文件是**项目级方法资产**，随仓库入 git、随 tag 走版本 —— 换机 `clone` 即得。
> 本机专属的环境坑（写盘 / git 引用 / 缓存脏）不在这里，而在**不入 git** 的
> `.workbuddy/memory/MEMORY.md`，因为那些是"这台机器"的属性，不是项目的属性。

## 适用场景（何时加载）

任何要**动这个仓库**的会话：改 `review_tool/` 代码、改评分规则、批量改复盘 md、
动 `reviews.db`、发版本、换机迁移。加载后按下面的口径执行 ——
**别凭直觉重新定义口径**，这个项目里几乎所有"看起来该这么改"的地方都有历史拍板。

---

## 0. 范围边界（先划清）

- **本项目 = 个人健康 / 复盘系统**：md 复盘 → `review_tool` → `reviews.db` → 评分 / 熔断 / 报告。
- ⛔ **不混"重装备份 / win-reinstall-toolkit"那套** —— 那是跨项目基础设施，与本系统**相互独立**。
  不要在本仓库文档里引用备份脚本，也不要把本仓库内容写进备份清单。
- **不在本仓库的资产**：助手人格 / 协作准则在用户级记忆 `~/.workbuddy/MEMORY.md`；
  跨项目通用 SOP 在用户级 `~/.workbuddy/skills/`（`sqlite-safe-migration`、`nmpa-cosmetic-record`）。
  用户级资产怎么保管**不属本仓库职责**，本仓库只保证项目级 skill 随代码入库。

---

## 1. 权威归属（最重要的一条，先记它）

改数据前先问"这件事谁说了算"。四类对象四个权威，混了就会互相覆盖：

| 对象 | 谁说了算 | 怎么收敛 |
| --- | --- | --- |
| 四维分 / 系统分（数据块 + 「六、四维评分」表） | **数据库** | `recompute-scores --apply && sync-docs`；⛔ **绝不手改 md 里的分数** |
| 打卡勾选（`personal_tracks`） | **源 md** | `doctor [打卡对账]` 检测 → `ingest --prune-tracks` 清理（默认关闭） |
| 一般字段（睡眠 / 时长 / 热量 / 结论文本…） | **源 md** | `ingest` 重新入库；upsert 默认 COALESCE 不擦数据 |
| 口径本身（分档 / 阈值 / 熔断参数） | `config.py` | 改完**必须**重算 + 回写文档，否则库与文档分叉 |

**为什么分数必须归库**：文档里的分数是派生值，写入端与人读端双向可写 ——
规则一改、库按新口径重算，下一次 `ingest` 又被文档里的旧值覆盖回去，口径变更无法生效。
`sync-docs` 把两处一起渲染成库值，双向覆盖问题才根除。

---

## 2. 评分与熔断口径（v1.4.0–v1.4.4 定版）

- **分档**：合格线以上维持 `5 / 7 / 9`（踩线分）；合格线以下按
  `config.SCORE_THRESHOLDS[*]["sub_floor"/"sub_ceil"]`（默认 1–4，可直接取整）切带，
  `idx = int(value / ok * n)` —— **用整数取带，不用 `round()`**，规避浮点 + 银行家舍入的边界抖动。
- **系统分** = 四维均值（四维齐全才算，保留 2 位小数）。
- **缺失子项**：整项剔除、剩余权重重新归一（健康分为加权模型；工作 / 学习 / 生活为时长分档）。
- **熔断**（`config.FUSE_RULES`，CLI `fuse`，有绝对熔断时 rc=1）：
  - 绝对 = 任一维度连续 `days`(3) 天 < `threshold`(6)；
  - 相对 = 近 `recent_days`(7) 日均值 vs 之前 `baseline_days`(28) 日均值，偏离 ≥ `drift`(1.0)；
  - 连续超过 `long_run_days`(14) 天 → 报告显式提示"绝对阈值对该维度已失去分辨力"，改用相对信号。
  - **别把两个信号当一回事**：绝对信号在"长期低分"分布上近乎恒真，分辨力来自相对基线。
- **`doctor` 口径唯一**：结论与退出码都走 `is_healthy()`；新鲜度 / 分数一致性 / 打卡对账 / 熔断
  一律**建议性**（只提示不拦）。要加新体检项时，先决定它是否影响 `is_healthy`，别各写一套记账。

---

## 3. 运动时长口径（v1.3.1–v1.3.2 定版）

- **训练日没填 = 没练**：`exercise_min=0` / `exercise_src='zero'`，**计入达成分母**（二态，无"未记录"豁免）；
  非训练日保持 `NULL`；手填 `0` 记 `'record'`（明确记录 ≠ 口径兜底）。
- **描述折算**：md「二、今日三件事」命中 `config.BODYWEIGHT_MOVES` → 确定性模型折算
  （净执行 + 组间休息，单日 clamp 10–45min），`src='derived'`。
- ⛔ **只扫「二、今日三件事」**，不扫「七、AI 评价与建议」（后者会引用别的日期，
  真实误判来源：9/20 评语写"你在 9/19 做过 100 个俯卧撑"）。「一个改进点 / 明日 Top 3」也不扫 —— 那是计划不是记录。
- **字段优先、不叠加**：`运动时长_min` 已有数值时以字段为准，折算不生效。
- `exercise=0` 时健康分的运动子项按**差档**计（不是整项剔除）—— 这是确定性结果，别当 bug 改。

---

## 4. 文档规约（v1.3.3 定版）

- **统一现行模板**：`一、日常打卡 … 六、四维评分 / 七、AI 评价与建议 + 附录 · 系统数据`；
  `星期` 一律写全称（星期一…星期日），标题同步。
- **语雀导入件（`2026-07/*` + `08-04`）保留九段式原文附录**，不强套新模板（会丢工作/学习/生活/偏离分析）；
  其现行形态即转换口径；但**数据块仍随库同步**。
- **缺「七、AI 评价与建议」= 当日无 AI 建议**（内容事实），不补空占位。
- **目录职责**：`复盘/YYYY-MM/` 是标准源（`ingest` 只扫这里）；`收件箱/`、`历史源复盘/`
  不参与 ingest，各带 README 说明。
- **批量改文档** → 用 skill **`doc-corpus-normalize`**（探测 → parse 基线 → dry-run → apply →
  逐字段 diff → 入库后快照比对），别直接批量替换。

---

## 5. 数据库规约

- **SQLite `reviews.db` 是唯一数据源**；schema 走 `PRAGMA user_version` 幂等迁移（当前 **v4**）。
- **改 CHECK 只能重建表**，重建必须走全覆盖流程：
  备份 → 副本验证 → 显式事务 → 逐列 diff → 落真库（详见用户级 skill `sqlite-safe-migration`）。
- **`reviews.example.db` 必须与当前 schema 同版**（`tests/test_example_db.py` 守卫），
  否则新用户复制后首次 ingest 会被 CHECK 拒绝。
- schema 外的遗留列迁移时按**列交集**搬运，数据留档 `.workbuddy/backup/`；不存中间计算产物。
- **`reviews.db` 可从 git 里的 md 100% 重建**（实测 49 天 / 343 打卡逐字段 0 差异）——
  所以库里出现疑问时，最有用的动作是"从零重建再逐字段比对"，而不是盯着真库猜。

---

## 6. 工程约定

- **零依赖**：纯标准库。测试用 `unittest`（当前 293 项），`ruff` 在 `envs/default/Scripts`（托管 python 里没有）。
- **CI 是阻塞的**：从仓库内 md 从零重建数据库 → `doctor` / `recompute-scores` / `sync-docs --check`
  **阻塞**（对账干净、分数与字段重算一致、md 无需回写）；`fuse` 不阻塞（人生指标告警）。
  矩阵 3.10–3.13。
- **四层架构（v1.5.0）**：`core`（零 I/O 纯规则）→ `storage`（SQLite 唯一出入口）→
  `pipeline`（md ↔ 库）→ `reports`（读库产出）。依赖**只能自上而下**，
  由 `tests/test_architecture.py` 用 ast 强制；`import sqlite3` 只准出现在 storage；
  `config.py` 留包根（可配置层，历史文档引用不失效）。新增模块必须归入对应层。
- **CLI 参数单一来源**：`__main__.py` 是**纯路由**（`ROUTES` 表 + 原样透传 argv），
  参数只在各模块 `main(argv)` 里定义一次；顶层统一拦截 `<子命令> -h`
  （否则 `ingest -h` 会真的跑一遍入库）。
- **文档分工**：`README.md` 讲怎么用；`docs/设计说明.md` 放规则 / 口径 / 字段 / 变更日志；
  `docs/迁移指南.md` 讲换机；`review_tool/README.md` 是包级速查。
- **版本节奏**：语义化 commit **逐 feature 单独提交** + 打 tag（小幅 `x.1`，重大升级主版本 +1），
  `main` fast-forward 推 GitHub（`deTian0/DailyLumen`）。每轮收尾都要更新
  `pyproject.toml` / `review_tool/__init__.py` / `README.md` 版本头 / 变更日志，四处对齐。
- 🔬 **「假装自己是 CI」演练**（挖漂移最有效）：删库或建临时库 → 用源 md 从零重建 →
  与真库**逐字段逐行**比对（不只看日期集合）。v1.4.2 的 17 条陈旧打卡键就是这么挖出来的。

---

## 7. 交付流程（5 步协议）

1. **读 memory** —— `.workbuddy/memory/MEMORY.md`（本机坑 + 指针）+ 最近日志
2. **执行** —— 按本 skill 的口径动手；每步之后**复核**（文件计数 / parse 基线 / 快照 diff）
3. **输出** —— 结论先行、表格 + 文件定位、简明中英混排
4. **present_files** —— 把新产出的交付物推给用户看
5. **写执行摘要** —— 追加到 `.workbuddy/memory/YYYY-MM-DD.md`（append-only）

---

## 8. 换机 / 迁移（v1.4.5 定版口径）

**git 里有什么**：全部代码 + 测试 + CI + 全部复盘原文 + 空库模板 + 三个项目级 skill（`dailylumen-conventions` / `daily-review-intake` / `doc-corpus-normalize`）。

| 路径 | 迁移动作 |
| --- | --- |
| `reviews.db` | **手工搬运**（不进 git）。不带也行 —— 可从 md 重建；带了就照旧跑一次 `ingest` 核对"0 处不一致" |
| `.workbuddy/memory/` | **不迁移** —— 项目口径已抽象为本 skill（入 git）；本机坑与日志随机器丢弃 |
| `.workbuddy/backup/` | **不迁移**（DB 快照 + 一次性脚本 + `archived/`，留档价值为主） |
| `.workbuddy/automations/` | 不迁移（自动化执行摘要）。**本项目当前无任何定时任务**，无需重建调度 |
| `exports/` | **重建**（`python -m review_tool export`） |
| `__pycache__/`、`.ruff_cache/` | **重建**（自动重生 / 重跑 ruff） |

**本项目不再需要任何定时任务**（v1.4.6 起）：原「晨间收集自动化」（每天 08:30）已删除 ——
素材改为**用户手动投递**（对话里直接发截图 / 文档 / 文字简报），由按需加载的 skill
**`daily-review-intake`** 处理。所以换机后**既不用搬记忆、也不用重建调度**，
唯一的手工动作就是把 `reviews.db` 拷过来。

> 完整步骤 / 验证清单见 [`docs/迁移指南.md`](../../../docs/迁移指南.md)。

---

## 9. 深潜指针（别重复造）

| 想知道 | 去哪 |
| --- | --- |
| 评分公式 / 字段含义 / 每次变更的来龙去脉 | `docs/设计说明.md` |
| 日常怎么用 / CLI 全集 / 数据块格式 | `README.md` |
| 换机怎么落地 | `docs/迁移指南.md` |
| **把素材变成当日复盘（发截图 / 发文档 / 总结对话）** | skill **`daily-review-intake`** |
| 批量改历史文档 | skill `doc-corpus-normalize` |
| 安全的库迁移 / 重建可复现性自检 | skill `sqlite-safe-migration`（用户级） |
| 模块级速查 | `review_tool/README.md` |

---

## 10. 易踩的坑（工程类，机器无关）

1. **`.gitignore` 整目录规则会让白名单静默失效**：必须写 `.workbuddy/*` + `!.workbuddy/skills/`。
   写成 `.workbuddy/` 会连目录一起排除，git 不再向下遍历，`!` 规则不报错也不生效。
   `tests/test_repo_layout.py` 把这条钉死了 —— 别"顺手清理"回去。
2. **改文件别用 Python 的文本模式写**：`open(p, "w")` 会在 Windows 上把行尾改成 CRLF，
   而 `.gitattributes` 要求 `eol=lf`。用 `open(p, "rb"/"wb")` + `replace(b"\r\n", b"\n")`。
3. **改服务端权威字段 = 白改**：md 里的分数、`ingest` 能覆盖的普通字段，改 md 只是临时状态，
   下一次 CLI 跑动就归位 —— 要改请改 `config.py` / 代码再走 CLI 收敛。
4. **`upsert_personal_track` 只增不删**：规范 ID 一改（如裸 `movefree` → `movefree@noon`），
   旧键永久滞留并**重复计依从率**。动的打卡项就要想着跑对账。
5. **本机专属的坑不写进本文件**：写盘不落盘、`git update-ref` 报成功不生效等属于
   "这台机器"的属性，记在 `.workbuddy/memory/MEMORY.md`（不入 git）。换机后若不复现就删掉。
   对应的**可执行动作**见用户级 skill `safe-write`（写后回读校验 + git 引用核对修复）。

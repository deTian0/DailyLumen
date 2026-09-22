---
name: doc-corpus-normalize
description: 批量把「历史格式不统一的 md 文档语料」标准化到现行模板，并保证解析/入库结果可证明无损。适用于 DailyLumen 复盘文档批量整改（旧模板章节、星期简写、过时章节名），也可套用到任何「md 是数据源、有解析器、有数据库」的项目。触发词：旧格式文档转换、批量标准化、文档归位、格式统一、批量改复盘文档。
agent_created: true
---

# 文档语料批量标准化（可证明无损）

## 适用场景

一批历史 md 因模板迭代而格式混存（旧模板 / 中间代 / 现行），需要统一；同时这些 md 是**下游解析器 + 数据库的数据源**，改动必须能证明「除了要改的东西，别的都没变」。

## 铁律

1. **先探测，再动手**：按格式分组统计（章节编号风格 / 标题写法 / 数据块键），产出「待标准化清单」，别凭印象批量替换。
2. **先建基线，再改文件**：对每个待改文件跑一次解析器，把结果 dict 存下来当基线。
3. **预演模式**：脚本必须支持 dry-run（默认不写盘），先看「改哪些、字段差异是什么」，确认后加 `--apply`。
4. **逐字段 diff + 允许清单**：改完立刻重新解析比对，只允许预先声明的字段变化（如 `weekday`）。出现非预期差异立即停止并回滚。
5. **不改有信息价值的历史形态**：若老文件的原始叙述比新模板更细（如九段式 vs 七段式），**保留原样**，不要为了整齐而丢信息。判断标准：转换后信息量是否下降。
6. **缺席 ≠ 缺陷**：某章节缺失可能代表「当日确实没有该内容」，不要塞空占位充数。
7. **⛔ 分数不要手改**（v1.4.0 起）：数据块里的四维分 / 系统分是**库渲染出来的**，手改会被下一次 `sync-docs` 覆盖，且改完 `ingest` 又会把旧值写回库。要做到「改口径」请走 CLI（见步骤 4），不要在 md 里动分数。
8. **每步复核**：写完文件立刻数文件数 / grep 关键行 / 重跑解析。本机（WorkBuddy on Windows）存在写盘不稳定现象，回报成功不等于落盘。

## 执行步骤

### 1. 探测格式分布

写一个只读探测脚本（放 `.workbuddy/backup/`，不进交付物）：

- 逐文件提取：标题行、章节列表、数据块键值、模板特征串
- 输出「格式版本分布」+「待标准化明细」，人工确认范围

```python
# 关键片段：章节提取
H = re.compile(r"^(#{1,3})\s*(.+)$", re.M)
headers = [m.group(2).strip() for m in H.finditer(text)]
```

### 2. 记录解析基线

```python
from review_tool.parse import parse_file
base = parse_file(path)
base.pop("_personal_tracks", None)   # 打卡单独比
```

### 3. 预演 → 应用（同一脚本）

转换脚本自带 diff 校验，输出格式：`变更项；字段差异: {...}`，并在结尾汇总「非预期差异合计」——必须是 **0**。

脚本按一次性工具对待（放 `.workbuddy/backup/`，随批次归档，不入库）；**不要把它当成长期依赖**——凡是被 CLI 覆盖的能力，一律优先用 CLI。

### 4. 走正式 CLI，而不是一次性脚本

转换完 md 后用项目 CLI 收敛（`__main__.py` 是纯路由，参数只在各模块 `main(argv)` 定义一次）：

```bash
python -m review_tool ingest                    # 重新入库；重跑不该改动任何库值
python -m review_tool recompute-scores          # 试算：库值 vs 按字段重算（应为 0 差异）
python -m review_tool sync-docs --check         # 试算：md 是否需要按库回写（应为 0 篇）
python -m review_tool doctor                    # 结论须为「数据健康」，rc=0
```

- 改了评分规则才需要 `recompute-scores --apply && sync-docs`（库为准 → 回写文档）；
- **打卡对账**：`doctor` 会报「库中打卡行在源 md 找不到对应勾选」；清理用 `ingest --prune-tracks`（默认关闭，仅当打卡章节确实解析到才删）。源文本规范 ID 一改，`upsert_personal_track` 就会留下陈旧键并**重复计依从率**。

### 5. 数据库侧验证（快照脚本在用户级 skill 里）

零依赖快照脚本：`C:/Users/63516/.workbuddy/skills/sqlite-safe-migration/scripts/sqlite_snapshot.py`

```bash
python "$SK/sqlite_snapshot.py" take review_tool/reviews.db before.json      # 改动前
python "$SK/sqlite_snapshot.py" diff review_tool/reviews.db before.json --allow <允许字段>
```

更狠的一招（**推荐**）：**「假装自己是 CI」** —— 删掉/换个临时库，只用仓库内 md 从零重建，再与真库**逐字段逐行**比对（排除 `ingested_at`）。集合级检查（日期集合、行数）看不见行级漂移；这一招挖出过 17 条陈旧打卡键。完整说明见 `sqlite-safe-migration` 的「重建可复现性自检」一节。

### 6. 收尾

- 需要丢弃的残件（如零数据空模板）：先 `cp` 到 `.workbuddy/backup/archived/` 再移除
- 目录职责补 README（尤其空目录：不进 git，恢复时需手动重建）
- 语义化提交：`fix` / `data` / `docs` 分开；打 tag；推送后核对 `git ls-remote`
- 记忆里只留**指针**（如「批量改文档 SOP → 见 skill doc-corpus-normalize」），不要复制本文件正文

## 事故兜底

工作区文件意外大面积消失时（本机出现过：一次 `git rm` 后整个数据目录被清空）：

```bash
git status --short            # 确认是 D（工作区丢失）而非 HEAD 丢失
git restore --staged --worktree -- <目录>   # 从 HEAD 恢复
```

数据源 DB 不受工作区抖动影响，但仍要复核 `COUNT(*)` 与 `PRAGMA integrity_check`，然后**重跑**转换脚本（因为改动已被回滚）。

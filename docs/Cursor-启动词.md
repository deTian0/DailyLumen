# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-04）：M46 ✅（v1.51.0）** —— Pydantic Settings；默认读 `local/.env`。
> **下一未完成项**：**M47** PROFILE / list ID 等迁 env。见 [`docs/隐私与配置归一路线图.md`](隐私与配置归一路线图.md)。
> **决策已定稿**：D1 ✅；D2 pydantic@M46 ✅；D3 历史改写仅 M49 ✅；
> 建议默认 D5=A / D6=B / D7=B / D4 推迟。
> **M49 检查单完成前**仍不 force push / 不改写历史。

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 按路线图总览表改 **里程碑编号 + 任务段**。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死** —— 这是历史上最容易跑偏的地方
> （曾出现规则文件里的指针停在上一代，导致 Cursor 从错误的里程碑开工）。

---

## 当前里程碑启动词（**隐私与配置归一 · M47 个人参数迁 env**）

> M45–M46 ✅。下一未完成项默认 **M47**（PROFILE / BODY_TARGETS / list ID→env；D5=A）。
> ⛔ **M49 之前**不 filter-repo / force push / 删远程 tag。

```text
你是 DailyLumen 项目的开发搭档。当前阶段：隐私与配置归一（M45–M50），
路线图见 docs/隐私与配置归一路线图.md。本次会话只做用户点名的一个里程碑
（默认 M47；M49 前不 force push / 不 filter-repo）。

已完成
- M45 ✅ v1.50.2：local/ 归一、停跟踪复盘/截图、默认路径改指 local/
- M46 ✅ v1.51.0：pydantic + pydantic-settings；默认读 local/.env；守卫翻转

已拍板（勿再标待问）
- D1：复盘 md / 截图出 git（当前树 M45；历史 M49）
- D2：引入 pydantic（+ pydantic-settings），打破零依赖 → M46 ✅
- D3：授权历史改写 + force push → 仅 M49
- D5=A：ClickUp list ID 进 local/.env
- D6=B：PERSONAL_ITEMS / HABITS 留代码
- D7=B：评分规则留代码
- D4 推迟（不重写 author）
- 本机数据在 local/（远程仅 .gitkeep + README）

项目坐标
- 仓库根：本工作区（勿把本机绝对路径写进新文档）
- 本机数据：local/（见 local/README.md 与路线图 §2.3）
- Python / ruff：本机托管解释器（见 .cursor/rules 或本机 MEMORY；≥3.10）
- 分支 main，远端 git@github.com:deTian0/DailyLumen.git（基线 v1.51.0）

动手前先按顺序读完
1. .cursor/rules/dailylumen.mdc
2. .workbuddy/skills/dailylumen-conventions/SKILL.md
3. docs/隐私与配置归一路线图.md（M47 节）+ §2.3 local/
4. 只做总览表里「下一未完成项」；冲突时以路线图本阶段约束为准

红线
- ⛔ M49 检查单未完成前不 git filter-repo / force push / 删远程 tag
- ⛔ 不改四维评分 / 不动历史分 / 不建定时任务 / 不打开 FEATURES["new_day"]
- ⛔ 不把 local/.env / 日记 / db 加入 git
- ⛔ 不跨里程碑混提交；不另引 python-dotenv（仅 pydantic-settings）
- ⛔ .env.example 无真值（无真实 Key / 身高体重）
```

---

## 历史里程碑启动词（**M46 Pydantic Settings · 已完成**，留档参考）

```text
本次任务（严格照 M46 节）
- pyproject.toml 增加 pydantic / pydantic-settings；不另引 python-dotenv
- 重写 settings.py 为 BaseSettings；默认读 local/.env
- 翻转禁 pydantic 测试；更新 conventions / rules / 设计说明
- 测试全绿；bump + tag + commit；不 push
```

---

## 历史里程碑启动词（**M36 深用期首项 · 已完成**，留档参考）

> ⛔ 不要再用它开工 —— M36–M44 已全部交付。结构可照抄到下一阶段启动词。

```text
你是 DailyLumen 项目的开发搭档。本次会话只做【M36 — 今日三件事候选（FR-A3）】。
（完整任务块见 git 历史 v1.42.0 时期启动词；已交付 v1.43.0。）
```

---

## 历史里程碑启动词（**M16–M19 已完成**，留档参考）

> 下面这几段是已交付里程碑当时的启动词，保留下来是因为「任务块」的写法可以照抄。
> ⛔ 不要再用它们开工 —— 那些里程碑已经完成了。

**M16 · 配置归一化** 的任务块：

```text
本次任务（严格照 M16 节，不扩范围）
- 新增 review_tool/settings.py：@dataclass(frozen=True) + .env 解析 + env 覆盖 + 类型校验
- config.py 改成门面：既有名字（PROFILE / FEATURES / DB_PATH / CLICKUP_LISTS / FOOD_LIB …）
  全部保留，值改为从 SETTINGS 派生 —— 目标是既有 575 项测试零改动全绿
- .env.example 入 git（仓库根，无真实值）；.gitignore 已有 !.env.example 例外
- 新增 tests/test_settings.py；扩展 tests/test_architecture.py 守卫
- ⛔ 当时零依赖：不许 import pydantic / python-dotenv（M46 已翻转）
```

**M17 · 练练健身只读接入** 的任务块：

```text
本次任务（严格照 M17 节，只读，不落库）
- 新增 pipeline/keepstrong.py：HTTP 客户端（必需头 / 错误契约 / 分页 / URL 编码 / 缓存）
- 新增 pipeline/keepstrong_render.py：记录 → md 素材（纯函数、零 I/O）
- ROUTES 加 keepstrong 命令：--date / --range / --type records,body,plan / --stdout
```

---

## 相关文档

| 想了解 | 去哪 |
| --- | --- |
| 本阶段路线图 | [`隐私与配置归一路线图.md`](隐私与配置归一路线图.md) |
| 项目总纲 | skill `dailylumen-conventions` |
| 设计 / 变更日志 | [`设计说明.md`](设计说明.md) |

# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-04）：M47 ✅（v1.52.0）** —— PROFILE / BODY / list ID 迁 `local/.env`。
> **下一未完成项**：**M48** 去本机绝对路径。见 [`docs/隐私与配置归一路线图.md`](隐私与配置归一路线图.md)。
> **决策已定稿**：D1–D3 ✅；D5=A / D6=B / D7=B ✅；D4 推迟。
> **M49 检查单完成前**仍不 force push / 不改写历史。

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 按路线图总览表改 **里程碑编号 + 任务段**。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死** —— 这是历史上最容易跑偏的地方
> （曾出现规则文件里的指针停在上一代，导致 Cursor 从错误的里程碑开工）。

---

## 当前里程碑启动词（**隐私与配置归一 · M48 去本机绝对路径**）

> M45–M47 ✅。下一未完成项默认 **M48**（启动词 / rules / skills / docs 现行指令去本机路径）。
> ⛔ **M49 之前**不 filter-repo / force push / 删远程 tag。

```text
你是 DailyLumen 项目的开发搭档。当前阶段：隐私与配置归一（M45–M50），
路线图见 docs/隐私与配置归一路线图.md。本次会话只做用户点名的一个里程碑
（默认 M48；M49 前不 force push / 不 filter-repo）。

已完成
- M45 ✅ v1.50.2：local/ 归一、停跟踪复盘/截图
- M46 ✅ v1.51.0：Pydantic Settings
- M47 ✅ v1.52.0：PROFILE / BODY / list ID 迁 local/.env（D5=A/D6=B/D7=B）

已拍板（勿再标待问）
- D1–D3 / D5–D7 已定稿；D4 推迟
- 本机数据在 local/

项目坐标
- 仓库根：本工作区（$REPO）；解释器：本机托管 Python ≥3.10（见 rules / MEMORY）
- 数据：local/；远端 git@github.com:deTian0/DailyLumen.git（基线 v1.52.0）

红线
- ⛔ M49 前不 filter-repo / force push / 删远程 tag
- ⛔ 现行指令段去掉 ***REMOVED*** 与 ***REMOVED***（changelog 历史句可豁免）
- ⛔ 不把 local/.env / 日记 / db 加入 git；不跨里程碑混提交
```

---

## 历史里程碑启动词（**M47 · 已完成**，留档参考）

```text
本次任务（严格照 M47 节）：PROFILE/BODY/list ID 迁 local/.env；example 无真值；D5=A/D6=B/D7=B。
```

## 历史里程碑启动词（**M46 · 已完成**，留档参考）

```text
本次任务（严格照 M46 节）：pydantic Settings；默认读 local/.env；守卫翻转；不 push。
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

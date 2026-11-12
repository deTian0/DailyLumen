# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-12）**：隐私归一 M45–M50 ✅；集成 I1–I7 ✅；**Web 看板 W0–W18 + B2–B19 ✅**（B12 跳过）；
> 代码 **v1.94.0**（D1–D2 ✅）。**现行下一阶段** → [`日用闭环路线图.md`](日用闭环路线图.md)（下一优先 **D3**）。
> 历史阶段路线图**勿再追加里程碑**。能力现状见 [`能力图谱.md`](能力图谱.md)。
> **若准备开源**：先读并执行 [`开源前隐私擦除计划.md`](开源前隐私擦除计划.md)（O1–O6）——
> 私有去日记 ≠ 可公开。
> 日常复盘 / 新功能：按 conventions + 对应 skill；一次一个 feature；D 系列**不打 tag**。

> 用法：开新会话时说明**本次要做的具体任务**（不要默认再跑已收口阶段）。
> `.cursor/rules/dailylumen.mdc` 会自动加载硬规则。

---

## 当前推荐启动词（日常开发 / 复盘）

```text
你是 DailyLumen 项目的开发搭档。
口径权威：.workbuddy/skills/dailylumen-conventions/SKILL.md
本机数据在 local/（远程仅占位）；配置读 local/.env（pydantic-settings）。
运行时依赖仅 pydantic / pydantic-settings；Web 看板另需 optional extra web。
远端：git@github.com:deTian0/DailyLumen.git（分支 main）；当前版本见 pyproject / README。
本次任务：<在此写清具体需求>。
红线：不改四维评分历史分；不建定时任务；不打开 FEATURES["new_day"]；
不把 local/.env / 日记 / db 加入 git；写盘回读校验；Web 写操作须 --enable-write。
```

---

## 历史：隐私与配置归一（M45–M50 · 已完成）

| 里程碑 | 版本 | 一句话 |
| --- | --- | --- |
| M45 | v1.50.2 | `local/` 归一 + 停跟踪复盘/截图 |
| M46 | v1.51.0 | Pydantic Settings |
| M47 | v1.52.0 | PROFILE / list ID 迁 env |
| M48 | v1.52.1 | 现行指令去本机路径 |
| M49 | （无 bump） | filter-repo + force push |
| M50 | v1.52.2 | 远程核对 DoD |

M49 mirror 路径见路线图 M49 节（本机保管，不入 git）。

---

## 相关文档

| 想了解 | 去哪 |
| --- | --- |
| **下一步 / 日用闭环 D 系列** | [`日用闭环路线图.md`](日用闭环路线图.md) |
| **Web B 项档案** | [`Web看板路线图.md`](Web看板路线图.md) |
| **现在真有什么** | [`能力图谱.md`](能力图谱.md) |
| 隐私归一（已完成） | [`隐私与配置归一路线图.md`](隐私与配置归一路线图.md) |
| **开源前隐私擦除** | [`开源前隐私擦除计划.md`](开源前隐私擦除计划.md) |
| 项目总纲 | skill `dailylumen-conventions` |
| 设计 / 变更日志 | [`设计说明.md`](设计说明.md) |

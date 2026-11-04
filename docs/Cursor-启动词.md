# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-04）：M48 ✅（v1.52.1）** —— 现行指令去本机绝对路径指纹。
> **下一未完成项**：**M49** 历史擦除 + force push（先 mirror）。见 [`docs/隐私与配置归一路线图.md`](隐私与配置归一路线图.md)。
> **决策已定稿**：D1–D3 ✅；D5=A / D6=B / D7=B ✅；D4 推迟。
> **M49** 须按检查单执行；本会话再确认 force push。

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 按路线图总览表改 **里程碑编号 + 任务段**。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死**。

---

## 当前里程碑启动词（**隐私与配置归一 · M49 历史擦除**）

> M45–M48 ✅。下一默认 **M49**（filter-repo + force push；先仓库外 mirror）。
> D3 已原则授权；执行前须勾完检查单 + 本会话再确认。

```text
你是 DailyLumen 项目的开发搭档。当前阶段：隐私与配置归一（M45–M50），
路线图见 docs/隐私与配置归一路线图.md。本次会话只做 M49（或用户点名项）。

已完成
- M45–M48 ✅（local/ 归一；Pydantic；PROFILE 迁 env；去本机路径指纹）

M49 检查单（须全部勾上再动手）
- D3 原则授权已记录
- 本会话确认：对 origin 执行 force push / 删不清净 tag
- 已 git clone --mirror 到仓库外安全路径（勿放进 local/）
- 清理路径对照附录 A
- D4 推迟（不重写 author）

项目坐标
- 仓库根：$REPO（当前工作区）；数据：local/
- Python ≥3.10 + pip install -e .；远端 git@github.com:deTian0/DailyLumen.git
- PowerShell：用 ; 不用 &&

红线
- 先 mirror，再 filter-repo，再 force push
- 不把 local/.env / 日记实体加入 git
- 清不净的 tag → 删本地+远程并记入路线图
```

---

## 历史里程碑启动词（**M48 · 已完成**）

```text
现行指令段去掉本机用户目录与仓库绝对路径；changelog 历史句可豁免；数据在 local/。
```

## 历史里程碑启动词（**M47 / M46 · 已完成**）

```text
M47：PROFILE/BODY/list ID → local/.env。M46：pydantic Settings。
```

---

## 相关文档

| 想了解 | 去哪 |
| --- | --- |
| 本阶段路线图 | [`隐私与配置归一路线图.md`](隐私与配置归一路线图.md) |
| 项目总纲 | skill `dailylumen-conventions` |
| 设计 / 变更日志 | [`设计说明.md`](设计说明.md) |

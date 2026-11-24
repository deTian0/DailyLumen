# Security Policy

## 支持范围

请报告与 **DailyLumen 本仓库代码**相关的安全问题，例如：

- 凭据或密钥被写进跟踪文件 / CI 日志的风险
- `serve` / Web API 鉴权绕过、未授权写操作
- 路径穿越、任意文件读写（尤其是 `local/` 之外）
- 依赖中可被本项目触发的高危漏洞（请附最小复现）

以下**不在**本政策默认受理范围：

- 本机 `local/` 被其它软件或系统账号读取（属于部署环境隔离）
- 用户主动把仓库转 public 后，git **历史**里曾存在、但已按开源擦除计划处理的内容争议（见 [`docs/开源前隐私擦除计划.md`](docs/开源前隐私擦除计划.md)）
- 第三方服务（ClickUp / 练练 / DeepSeek）自身的账号安全

## 如何报告

请使用 GitHub **Private vulnerability reporting**（仓库 Security → Advisories → New draft advisory）。

- ⛔ **不要**在公开 issue / PR / 讨论区贴 POC、token、或个人数据。
- ⛔ 本文件**不**公布个人邮箱；若仓库尚未启用 private advisory，请先开一个**不含细节**的 issue 标题（例如「请求开启 private advisory」），维护者开启后再私密跟进。

报告里尽量包含：影响版本（git tag 或 commit）、复现步骤、预期 vs 实际、是否已有可利用面。

## 密钥与本机数据

- 真凭据只放 `local/.env`（gitignore）；模板见 [`.env.example`](.env.example)。
- 复盘正文、SQLite 个人库、截图一律在 `local/`，不得提交。
- Web 面板默认绑定 `127.0.0.1`，依赖 `DAILYLUMEN_WEB_KEY`；写接口需显式 `--enable-write`。不要把服务裸暴露到局域网或公网。

## 披露节奏

维护者为个人项目，响应可能不在工作日 SLA 内。确认有效后会优先修 main，并在设计说明变更日志中简要记载（不披露未修复细节）。

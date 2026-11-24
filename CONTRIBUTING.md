# Contributing to DailyLumen

感谢关注。本仓库是个人每日复盘 / 生活管家系统；欢迎 issue 与 PR，但请先读完本节边界。

## 先读什么

| 文档 / skill | 用途 |
| --- | --- |
| [`.workbuddy/skills/dailylumen-conventions/SKILL.md`](.workbuddy/skills/dailylumen-conventions/SKILL.md) | **口径权威**：权威归属、四维评分、熔断、schema、工程约定 |
| [`README.md`](README.md) | 怎么跑 CLI / Web |
| [`docs/设计说明.md`](docs/设计说明.md) | 规则、字段、变更日志 |
| [`docs/能力图谱.md`](docs/能力图谱.md) | 现有能力与证据 |

改评分规则、schema、复盘 md 约定或发版本之前，**先加载 conventions**，不要凭直觉重定口径。

## 绝对不要提交

- `local/**` 实体（复盘 md、截图、`reviews.db`、`local/.env`、exports…）——远程只允许 `local/.gitkeep` + `local/README.md`
- 根目录或任意路径的真实 `.env`、API Key、ClickUp / 练练 token、Web Key
- 个人日记、体征真值、用药/补剂真实方案、同事真名
- 把本机绝对路径写进代码或文档（用占位符）

配置模板用根目录 [`.env.example`](.env.example)；CI 非密钥夹具见 [`tests/fixtures/ci.env`](tests/fixtures/ci.env)。

## 开发约定（摘要）

1. **外部数据先落复盘 md，再 `ingest`**（禁止只写库不落 md）。
2. **不改四维评分历史分 / 权重**，除非 issue 明确授权且按 conventions 走重算 + `sync-docs`。
3. **`core/` 零 I/O**；SQLite 只经 `storage/`；前端不另算口径（R1）。
4. 一次一个 feature；Python 改动：`unittest` 全绿 + `ruff check`；前端改动：`npm test`（及必要的 `npm run build`）。
5. 版本四处对齐（`pyproject.toml` / `review_tool/__init__.py` / `README.md` 头 / 设计说明变更日志）由维护者在收口时处理；**贡献者 PR 不必自行打 tag**。

本地最小自检：

```bash
pip install -e .
python -m unittest discover -s tests -t .
ruff check
```

Web 相关另见 README「Web 生活管家面板」。

## PR 建议

- 说明动机、触及的层（core / storage / pipeline / reports / api / web / docs）。
- 若动到评分、熔断、schema、ingest 语义：写明是否需要重算 / 迁移，以及如何验证。
- 附上相关测试名或手工复现步骤；涉及 ClickUp / 练练时**只用 mock**，不要贴真实 list ID 或 token。

## 许可证

**LICENSE 暂缓**（维护者 2026-11-23 定调）：仓库尚未选定 SPDX；在根目录出现 `LICENSE` 之前，请勿假设可再分发或商用。

第三方：`.workbuddy/skills/life-decision-guide/` 为 [HowToLiveBetter](https://github.com/eternity4719/HowToLiveBetter) 的 `skills/` 副本，适用上游 **MIT**（目录内 [`LICENSE-CODE`](.workbuddy/skills/life-decision-guide/LICENSE-CODE)，Copyright (c) 2026 eternity4719）；书正文为 CC BY 4.0，本仓未收录。

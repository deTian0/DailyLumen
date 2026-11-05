# DailyLumen · Web 看板路线图

> **用途**：承载 `docs/Web看板PRD.md` 第 8 节 W0→W11 的里程碑执行记录。
> **权威顺序**：`docs/Web看板PRD.md`（要什么/为什么）→ 本文（按什么顺序做、做到哪了）。
> **不是**里程碑内容的重复定义——每条只记「做了什么、验收结果、commit/tag」。
> **基线**：`v1.60.0`；全量测试 1029 通过 / 2 跳过（`python -m unittest discover -s tests -t .`）。

---

## 0. W0 拍板记录（2026-11-05）

### D-1：PRE-03 pydantic 例外

**拍板**：允许 `review_tool/api/` 使用 pydantic（FastAPI 请求/响应模型）。
同步修改：
- `tests/architecture/test_architecture.py`：`LAYERS` 加入 `"api"`；`ALLOWED["api"]` = 可依赖 core/storage/pipeline/reports/integrations/api；其余层不得依赖 `api`；`TestSettingsPydanticStack` 的 pydantic 白名单从「仅 `settings.py`」扩为「`settings.py` 与 `api/` 下所有文件」。
- `.cursor/rules/dailylumen.mdc` 与 `.workbuddy/skills/dailylumen-conventions/SKILL.md`：依赖收敛文案补充「`review_tool/api/` 例外：可使用 pydantic（FastAPI 模型），范围不扩大到其余业务层」。

### D-2：5 个「幽灵 M」文件

**结论**：`.workbuddy/skills/clickup-tracking/SKILL.md`、`docs/设计说明.md`、`review_tool/pipeline/clickup.py`、`review_tool/pipeline/clickup_pull.py`、`tests/settings/test_config.py` 五个文件 —— **索引(blob hash) == 工作区(blob hash)，内容零差异**；`git diff`/`--stat`/`--raw`/`--ignore-all-space` 均为空。

根因：`git ls-files --debug` 显示索引缓存的 `size` 字段与磁盘实际大小不一致（例：`clickup.py` 索引记 24139，磁盘实际 23578，差值 561 恰好等于该文件 LF 行数 561——据此**推断**：历史上某次写入让工作区文件短暂是 CRLF，索引按那时的大小缓存了 stat，之后文件被改回 LF，内容 blob 不变但 stat 缓存没同步）。可能的诱因是系统级 `core.autocrlf=true` 与用户级 `core.autocrlf=input` 两层配置不一致，或本机工具写文件时用了文本模式；**具体是哪次操作没有证据，未能确认**。

**处理**：`git update-index --refresh` 重新写入正确的 stat 缓存（不改内容，纯刷新索引记录的 size/mtime）。刷新后 `git status` 干净。此操作**无害且可逆**（未丢弃任何改动，仅修正 stat 缓存）。

### D-3：lint 基线（PRE-09）

本机此前无 ruff，已用 `uv tool run ruff@0.15.0` 验证。**存量违规 32 处**，逐一甄别后：

- **16 处是误报**：`review_tool/pipeline/keepstrong.py` 故意再导出 `integrations.keepstrong`
  的符号供旧测试用（`tests/pipeline/test_keepstrong_*.py` 直接 `ks.encode_query` 等），
  不可删除——已在 `pyproject.toml` 加 `[tool.ruff.lint.per-file-ignores]` 白名单该文件的
  `F401`，而不是逐处加 `# noqa`（更不容易在未来新增真未用导入时被掩盖）。
- **其余 16 处是真实可安全修复的存量问题**（import 排序 I001、`UP035` 旧式类型导入、
  `F541` 空 f-string、`F401` 真未用导入、`B905` `zip()` 缺 `strict=`）：已用
  `ruff check --fix .` 清理（`B905` 的两处手动补 `strict=False`，保持原有「允许不等长」
  的实际语义不变，不引入新的长度校验行为）。**改动前后跑过全量 1029 测试，OK**，
  确认是纯格式/风格修复，无行为变化。随 v1.60.1 单独提交（见 W0 commit 列表），
  不混入任何 Web 功能代码。

**结论**：ruff 现在**全绿**（`All checks passed!`），后续每个里程碑可以按「全仓 ruff 干净」
验收，不必再做「仅对比新增文件」的降级处理。

### D-4：其他 PRD §9 拍板项

均按 PRD 第 9 节「我的建议」执行：P0 按 W3/W4/W5 分步交付；AI 一键总结默认预览不落盘；图表首期嵌入现有 SVG；`import-history` 不出 Web；`serve` 默认只读，写操作需显式 `--enable-write`；设计草案 F* 编号收口到本 PRD 的 FR 编号（草案已在前序 commit 改为指向需求文档，本路线图不再使用 F* 编号）。

---

## 1. 里程碑状态表

| 里程碑 | 内容 | 状态 | commit | tag |
| --- | --- | --- | --- | --- |
| W0 | 清场 + 拍板 + 本路线图 | ✅ | `b71686b`（lint 清零）+ 本文档提交 | `v1.60.1` |
| W1 | serve 壳 / health / 架构守卫扩 api 层 / optional extra | 未开始 | — | — |
| W2 | 只读编排抽取与对拍框架 | 未开始 | — | — |
| W3 | ClickUp 今日 API | 未开始 | — | — |
| W4 | 报告与分析 API | 未开始 | — | — |
| W5 | 前端脚手架 + P0 页面 + dist 入库 | 未开始 | — | — |
| W6 | 健康与学习督导查询 | 未开始 | — | — |
| W7 | 报表增强 | 未开始 | — | — |
| W8 | AI 预览 + mode 门禁 | 未开始 | — | — |
| W9 | P2 写操作第一批 | 未开始 | — | — |
| W10 | P2 写操作第二批 | 未开始 | — | — |
| W11 | 前端自绘图（可选） | 未开始 | — | — |

> 本表随每个里程碑完成实时更新；详细验收记录写在下方对应小节。

---

## 2. 里程碑详情

### W0 — 清场与拍板

- 清查 5 个幽灵 `M` 文件，确认无实质差异，刷新索引 stat 缓存。
- 记录 lint 基线（见上）。
- 提交 `docs/Web看板PRD.md`（之前未入库）与本路线图文档。

---

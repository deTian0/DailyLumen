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
| W1 | serve 壳 / health / 架构守卫扩 api 层 / optional extra | ✅ | 见 W1 详情 | `v1.61.0` |
| W2 | 只读编排抽取与对拍框架 | ✅ | 见 W2 详情 | `v1.62.0` |
| W3 | ClickUp 今日 API | ✅ | `clickup_queries` / `routes_clickup`，20 用例 | `v1.63.0` |
| W4 | 报告与分析 API | ✅ | `routes_reports`（周/月/ai-context/stats/doctor/fuse/charts），23 用例 | `v1.64.0` |
| W5 | 前端脚手架 + P0 页面 + dist 入库 | ✅ | 四页 + dist 入库 + `test_web_dist` | `v1.65.0` |
| W6 | 健康与学习督导查询 | ✅ | `life_queries` / `routes_life` + 生活管家页，12 用例 | `v1.66.0` |
| W7 | 报表增强 | ✅ | `week-done` / `streaks` / `day-help` + 3 个 tab，6 用例 | `v1.67.0` |
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

### W1 — serve 壳 / health / 架构守卫扩 api 层 / optional extra

**产出**：

- `pyproject.toml`：新增 `[project.optional-dependencies] web`（`fastapi==0.162.0` /
  `uvicorn==0.54.0`，钉版本）与 `[dependency-groups] dev`（`ruff==0.17.3` / `httpx==0.28.1`）；
  `uv.lock` 入库。
- `tests/architecture/test_architecture.py`（PRE-01）：`LAYERS` 加入 `"api"`；
  `ALLOWED["api"]` 可依赖其余全部层；新增 `TestApiLayerGuard` 断言「其余层不得依赖 api」+
  「fastapi/uvicorn 只准出现在 api/」；`TestSettingsPydanticStack` 的 pydantic 白名单从
  「仅 `settings.py`」扩为「`settings.py` 与 `api/`」（PRE-03 / D-1）。
- `review_tool/storage/db.py`：新增 `get_readonly_conn()`（SQLite URI `mode=ro` +
  `PRAGMA query_only`，库不存在抛 `FileNotFoundError`）——Web API 读库的唯一入口，
  物理上不可能通过它写库。
- `review_tool/api/`（新层）：
  - `health.py`：`build_health()` 白名单构造（`status/version/llm_mode/integrations/
    ai_enabled/db_present/readonly`），用 `review_tool.__version__` + `config.get_llm_mode()` +
    `integrations.flags.is_enabled()`，不读任何凭据字段。
  - `app.py`：`create_app()` 应用工厂——Host/Origin 中间件（默认仅回环，防 DNS rebinding
    与跨站写请求 PRE-07）、统一错误体 `{error:{code,message}}`、`/api/health`、dist 静态托管
    + SPA fallback（防路径穿越）、无 dist 时的提示页（503）。提供 `extra_routers` 参数作为
    **后续里程碑业务路由的标准接入点**（必须在 SPA 通配路由之前 `include_router`，
    不能在 `create_app` 返回后 `add_api_route`——否则会被 SPA 通配先截获，已用测试固定
    这条路由注册顺序约束）。
  - `serve.py`：`python -m review_tool serve [--host H] [--port P] [--dist DIR]
    [--enable-write]`；默认 `127.0.0.1:8765`、只读；非回环地址启动时打印安全警告；
    缺 `fastapi`/`uvicorn` 时给安装提示并退出码 2（不抛栈）。
- `review_tool/__main__.py`：注册 `serve` 路由（`_serve` 延迟 import `api.serve`，
  避免未装 web extra 时 `import review_tool` 就失败）。
- `tests/api/test_app_shell.py`：19 个用例，覆盖 health 形状/无密钥、Host 守卫、
  Origin 守卫（写方法）、自定义 allowed_hosts、404 统一错误体、未处理异常不泄露
  （用 `extra_routers` 正规接入，不用事后 `add_api_route`）、无 dist 提示页、
  SPA fallback、assets 静态资源、路径穿越防护、serve 缺依赖提示、`--host` 非回环警告。
  未装 `web` extra 时整组 `skipUnless` 跳过，不影响不装 Web 依赖的用户跑全量测试。
- 依赖收敛文案同步：`.cursor/rules/dailylumen.mdc` 规则 2、
  `.workbuddy/skills/dailylumen-conventions/SKILL.md` §6，补充
  「`review_tool/api/` 例外：可用 pydantic（FastAPI 模型），范围不扩大到其余业务层」。

**验收**：

- 架构守卫新断言通过（`api` 反向依赖会被拦住；fastapi/uvicorn 越界会被拦住）。
- `uv run python -m review_tool serve` 真实启动，`curl /api/health` 返回
  `{"status":"ok","version":"1.61.0",...,"readonly":true}`，伪造 `Host: evil.example.com`
  返回 403。
- 全量测试 1051 通过 / 2 跳过（新增 22 个：19 个 API + 3 个架构守卫）；`ruff check .` 全绿。
- `review_tool/__init__.py` 文档计数同步为 41 子命令。

---

### W2 — 只读编排抽取与对拍框架

**PRE-02 盘点结论**：body/coach/habits/nutrition/tutor/steward/promises/stats/correlate/
week_done/clickup_done/fuse/chart/analyze 的取数函数都接收外部 `conn`，可零改动复用；
缺口只有 `doctor.diagnose`、`day_close.assess_day_ready`、`ai_review.build_context`
（内部写死 `init_db`，会建库/迁移）→ 加可选 `conn=None` 注入，CLI 路径不变。
`finalize` / `day_help` 仅 `main`，留待 W7/W10 需要时再抽。

**产出**：`reports/analyze.py` 新增 `default_month` / `default_week` / `week_iso_years`；
`review_tool/api/queries.py`（只读查询编排，不依赖 fastapi）；`tests/api/test_queries.py` 25 例对拍。

**PRE-06 结论**：CLI `week N` 按周号聚合不变；Web 用 `year+week`，年不符 404、跨年混叠 409。

**验收**：全量 1076 通过 / 2 跳过；ruff 全绿。

---

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
| W8 | AI 预览 + mode 门禁 | ✅ | `ai_queries` / `routes_ai` + 报告页 AI 预览卡，门禁 409 | `v1.68.0` |
| W9 | P2 写操作第一批 | ✅ | `write_ops` / `routes_write`（--enable-write 才挂载、一次性 token、写前备份、回读校验）+ `WriteFlow` | `v1.69.0` |
| W10 | P2 写操作第二批（FR-J1 ClickUp 建任务/改状态 + FR-K1 ingest 单文件） | ✅ | `write_ops` 扩 `task_create` / `task_status` / `ingest`（list 白名单、INPUT_DIR 防穿越、写库前备份、写后回读）+ 今日页内联完成/新建、定稿→入库串联；FR-I2 读图日流程 / 练练写回顺延 | `v1.70.0` |
| W11 | 读图日流程（FR-I2）+ 本周节奏快照空态 | ✅ | `write_ops` 扩 `vision`（上传 ≤6 张 / 单张 ≤8MB / magic 嗅探 PNG·JPEG·WebP、临时目录 finally 清理、mode 门禁先于 I/O、later_wins 冲突预览）/ `inbox_archive`（防穿越、移到 `已处理/日期/`）/ `clickup_pull`（`collect` 纯拉取、写前备份、整天替换、回读条数）；复盘页读图卡 → 写 md → ingest、今日页快照空态按钮；练练写回 / 自绘图顺延 | `v1.71.0` |
| W12 | 「好用」导向 UI / 交互打磨 | ✅ | 今日待办分组（逾期默认折叠）+ 批量完成（单 token 一批 ≤20、逐条 CLI、逐条回读）；快照预览明列替换日期 before→after 与本周投影；读图缩略图（收件箱受限端点防穿越）；复盘四步进度条（doctor `day_ready` 单源）+ 今日页导流条；非 deepseek / 只读门禁收成一行；写按钮带动作名；「只读」文案按 health 动态；窄屏 ≤768px 适配 | `v1.72.0` |
| W13 | 写操作框架重构（为练练写回铺路） | ✅ | `write_ops` 拆为 `api/writes/{base,habits,review_md,clickup,ingest,vision}`，门面保留原导出；`confirm` 分派由 if/elif 改为 `@register(action, needs=...)` 注册表（`plan_out` 拒发未登记动作的 token）；`Today.jsx` 拆出 `components/today/*` + `lib/todos.js`；`app.css` 按区段拆 6 个文件（产物哈希不变）；行为不变 | `v1.73.0` |
| W14 | serve 最小鉴权 | ✅ | `DAILYLUMEN_WEB_KEY`（`local/.env`，未配置拒绝启动）+ `api/auth.py`（Bearer / `X-DailyLumen-Key`，`compare_digest`，`/api/ping` 免 key）+ 前端登录页（默认 sessionStorage、401 回登录页、blob 取图/下载） | `v1.74.0`（未打 tag） |
| W15 | 前端 Vitest 单测 | ✅ | Vitest 5.1 + jsdom + Testing Library（devDep 钉版本）；5 文件 24 例覆盖 `api.js`（key/401/blob）、`route.js`、`todos.js`（待办分组）、`WriteFlow`（预览→确认→失败重试重新预览）、`Login`；`WriteFlow.jsx` 补 `try/catch` 收起旧预览防复用 token | `v1.75.0`（未打 tag） |
| W16 | ECharts 自绘图 | ✅ | `/api/charts/{kind}.json`（复用 `fetch_*_series` / `moving_average` / `BODY_TARGETS`，R1 单源；`.json` 路由排在 `{kind}` 前防吞）+ 前端 `EChart.jsx` / `chartOption.js`，`Analytics` 改吃 JSON；旧 SVG 端点保留；echarts@5.6.0 钉版本；+6 后端 / +7 前端测试 | `v1.76.0`（未打 tag） |

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

---

## 二期里程碑详情（W14–W17）

### W14 — serve 最小鉴权（v1.74.0）

- **凭据**：`DAILYLUMEN_WEB_KEY` → `settings.web_key`（`repr=False`），只放 `local/.env`；根 `.env.example` 仅占位。本机 `local/.env` 原无此行，已用 `secrets.token_urlsafe(32)` 生成并**只追加**到末尾（回读确认原有字节未变；值未打印）。
- **后端**：`api/auth.py`（`extract_key` / `key_matches` / `requires_key`）；`create_app(web_key=...)` 中间件在 Host / Origin 守卫之后校验 `/api/*`，`/api/ping` 免 key 且只回 `{"ok":true}`；静态 dist 免 key；不接受查询串里的 key。`serve` 未配置 key → rc=2 + 提示。`create_app(web_key=None)` 仅供单元测试。
- **前端**：`pages/Login.jsx`（先 `/api/health` 校验再保存）；存储权衡——默认 **sessionStorage**（关标签页即失效，降低共用电脑 / 长期驻留风险），勾选「记住」才进 localStorage（换来免重复输入；两者对同源 XSS 同样暴露，本项目无第三方脚本、仅回环访问，风险可接受）。401 → 清 key、回登录页并提示「已失效」；侧栏「退出登录」。`<img>` / `.md` 下载改为带 key 取 blob（`AuthImage` / `DownloadButton`）。
- **验收**：`tests/api/test_auth.py` 17 例（无 key / 错 key / 对 key / 两种头 / 查询串不收 / 探针 / 静态免 key / 守卫顺序 / 未配置 key 拒绝启动 / key 不进控制台）；`test_web_dist` 断言本机 key 值不在 bundle。

---

### W15 — 前端 Vitest 单测（v1.75.0）

- **框架**：Vitest 5.1.0 + jsdom 31.0.0 + @testing-library/react 16.3.3（devDependencies，版本钉 `web/package-lock.json`）；`npm test` = `vitest run`；`vite.config.js` 加 `test` 段（jsdom、`src/test/setup.js` 每例后清 sessionStorage/localStorage/hash + 卸载组件、`restoreMocks`）。测试与源码同目录 `*.test.js(x)`，全部 mock `fetch`，不连真服务。
- **覆盖**（5 文件 24 例）：
  - `lib/api.test.js`：`authKey` 存储分流（sessionStorage / remember→localStorage）；请求带 `Authorization: Bearer` 且 key 不进 URL；POST JSON 体；401 清 key + 派发 `UNAUTHORIZED_EVENT` + 抛 `ApiError`、非 401 保留服务端错误体不清 key、网络失败 → `network`；`verifyKey` 不写存储不派发事件；`blobUrl` 带 key 取二进制。
  - `lib/route.test.js`：`hashPage` / `hashQuery` 解析。
  - `lib/todos.test.js`：`groupTodos` 逾期默认折叠 / 进行中排在有截止 open 前 / kind 标签随行 / 空分组不渲染；`weekDays` 周一开头 7 天含跨月。
  - `components/WriteFlow.test.jsx`：预览后显示等价 CLI、确认用预览 token；**确认失败旧预览收起、重试重新预览拿新 token**；`canConfirm=false` 不给确认按钮；带 body 走 JSON plan；只读折叠不发请求；门禁原因优先。
  - `pages/Login.test.jsx`：错 key 不保存、对 key 默认 sessionStorage、记住进 localStorage、空输入不发请求、`expired` 失效提示。
- **行为微调**：`WriteFlow.jsx` 的 `confirm` 包 `try/catch`——`api.writeConfirm` 抛错时 `setPlan(null)` 收起旧预览（服务端取 token 即作废，防止拿用过的 token 再点确认）；正常路径无变化，由新测试固定。
- **验收**：`cd web; npm test` → 5 文件 24 例全绿；`npm run build` 通过重建 `web/dist`；全量 Python 1208 通过 / 2 跳过；ruff 全绿。

---

### W16 — ECharts 自绘图（v1.76.0）

- **后端**：`api/queries.py` 加 `chart_series(conn, kind)`，复用 `reports.chart.fetch_*_series` + `core.body.moving_average` + `config.BODY_TARGETS`（R1 单源，不另算均线 / 目标带）。返回 `{"kind","dates","series","target"}`，序列带 `key/name/color/unit/values/type`；body 的 ma7 带 `dash`，nutrition 两条带 `yAxisIndex`。`routes_reports.py` 加 `GET /api/charts/{kind}.json`（`JSONResponse` + `no-store`）；**`.json` 路由须排在 `{kind}` 之前**（`{kind}` 默认 `[^/]+` 含点，否则吞成 `kind="trends.json"`），用测试固定。旧 SVG 端点保留。
- **前端**：`echarts@5.6.0`（首个前端运行时依赖，版本钉死）；`components/EChart.jsx`（init / dispose / resize 包装，SVG renderer）；`lib/chartOption.js` 纯函数 `buildChartOption` 把 JSON 转 ECharts option（目标带 markArea / markLine、双 yAxis、柱 / 线分派）；`pages/Analytics.jsx` 的 `ChartView` 由嵌 SVG 改为 `useAsync` 取 JSON → `EChart`。
- **对拍**：`tests/api/test_reports_api.py` +6 例（JSON == `chart_series`、trends 值 == `fetch_series` 列、body 含 ma7 + 目标带、nutrition 双轴、未知 404、`.json` 不被吞）；`web/src/lib/chartOption.test.js` 7 例。前端共 6 文件 31 例。
- **权衡**：bundle 283 KB → 1.31 MB（gzip 88 → 427 KB），换 tooltip / 缩放 / 图例切换；可接受。
- **验收**：`cd web; npm test` → 6 文件 31 例全绿；`npm run build` 通过；全量 Python 1214 通过 / 2 跳过；ruff 全绿。

---

## 收口：最终设计复查与清单（W0–W12，v1.72.0）

> 本节追加于 W12 提交后，作为 Web 生活管家面板一期收口记录；后续新里程碑另起文档，不在本节续写。

### 1. 设计复查结论

**四层架构 + api 守卫**：仍成立。`core ← storage ← pipeline ← reports` 单向依赖与「其余层不得 import `api` / Web 栈」由 `tests/architecture/test_architecture.py` 强制，W12 新增代码全部落在 `review_tool/api/` 与 `web/`，未触碰评分 / 归日。批量完成复用 `pipeline.clickup_task.run_status`，快照投影复用 `storage.db.load_clickup_done` + `pipeline.clickup_pull.collect`，复盘进度复用 `reports.day_close.assess_day_ready`（R1 单源）。

**后端可演进性**：
- 只读编排（`queries` / `clickup_queries` / `life_queries` / `ai_queries`）不依赖 fastapi，可被 CLI / 测试直接调用；对拍测试锁住与 CLI 同源。
- 写操作框架统一为 `plan_*`（预览 + `TokenStore` 一次性 token + 等价 CLI）→ `confirm`（`_WRITE_LOCK` 串行、写前备份、写后回读）。新增写类型（如练练写回）只需补一对 `plan_x` / `_apply_x` + 一条路由 + 前端 `WriteFlow` 的 `renderPreview`。
- 可改进点：`confirm` 的动作分派是 `if/elif` 链（10 种动作、9 个分支），再加类型前建议改成 `action → apply` 注册表；`write_ops.py` 已 713 行，建议按域拆成 `write_clickup` / `write_review` / `write_vision`。

**前端可维护性**：无路由 / 状态库依赖，`useAsync` + `lib/api.js` 单一取数入口，`WriteFlow` 统一预览→确认交互，`lib/route.js` 拆出 hash 查询避免循环依赖。风险点：`Today.jsx` 574 行、`app.css` 989 行，建议把待办分组 / 批量栏 / 快照预览拆到 `components/`，CSS 按页面拆分。

**安全面**：
- 回环绑定：`serve` 默认 `127.0.0.1`；非回环地址启动时显式告警（无鉴权）。
- Host / Origin：中间件只放行回环 Host（防 DNS rebinding），写接口校验 Origin。
- 写开关：写路由仅 `--enable-write` 时挂载；默认只读。
- Token：`secrets.token_urlsafe(24)`、5 分钟 TTL、一次性（`pop`），进程内存，重启即失效；批量完成一 token 对应一批（≤20）。
- 路径白名单：ingest 限 `local/每日复盘/`；收件箱归档与缩略图端点只接受纯文件名，`realpath` + `commonpath` 锁在收件箱顶层，magic bytes 嗅探类型，响应带 `no-store` / `nosniff`。
- 密钥不下发：`/api/health` 只给 integrations 布尔值；错误文案只提示 `.env` 键名，不回显值。

### 2. 已完成功能（按页面）

| 页面 | 功能 |
| --- | --- |
| 今日看板 | ClickUp 今日待办（逾期默认折叠 / 今日到期·进行中 / 无截止）、搜索、单条完成 + 批量完成、新建任务、今日已办（含回拨）、昨日收工灯 + 「昨日复盘还差几步」导流条、本周节奏 + 快照拉取（替换日期 before→after + 本周投影）、今日负荷、系统状态 |
| 生活管家 | 早报 / 健康 / 训练 / 营养 / 习惯 / 学习 / 承诺，习惯同步（预览→确认） |
| 复盘与报告 | 周报 / 月报 / 昨日上下文；复盘四步进度条；AI 预览；读图日流程（上传 / 收件箱缩略图 → 字段预览 → 写 md → ingest → 可选归档）；AI 草稿写入、定稿、入库 |
| 分析 | 指标趋势与相关性（与 CLI analyze 同源） |
| 体检 | doctor / fuse 同源只读结果 |
| 全局 | 只读 / 写开启状态按 `/api/health` 动态显示；非 deepseek / 只读时写卡折叠成一行说明；写按钮 aria-label 带动作名；焦点可见；窄屏 ≤768px 适配 |

### 3. 验证情况

- 全量测试 1184 通过 / 2 跳过；`uv run ruff check .` 全绿；`npm run build` 通过并重建 `web/dist`。
- 写路径全部用 mock / 临时库覆盖（W9–W12），未对真实 ClickUp / 真库执行确认。
- 浏览器（`serve --port 8793 --enable-write`，`llm_mode=workbuddy`）只点到预览：批量完成预览（2 条，逐条 CLI 正确）、快照预览（替换 4 天、本周投影）、复盘页门禁折叠与进度条、390px 窄屏无横向溢出；截图在 `local/screenshots/w12/`；测完已关闭 8793。

### 4. 已知问题 / 风险

- 服务无鉴权，安全完全依赖回环绑定 + Host/Origin；改监听地址会暴露全部数据。
- Token 在进程内存，重启后进行中的确认全部失效（设计如此）。
- 批量完成是逐条调用 ClickUp，非原子；部分失败会逐条回报，需要用户重试。
- 本周节奏依赖已入库的 `clickup_done` 快照，未拉取时全为 0（已有空态说明）。
- 缩略图端点每次读原图，无缩放；收件箱图片多时首屏流量偏大（已 `loading="lazy"`）。
- `Today.jsx` / `write_ops.py` / `app.css` 体量偏大，见第 1 节拆分建议。
- 对比度只做了人工检查，未用辅助技术做完整 WCAG 验证。

### 5. 建议后续里程碑

1. 练练写回（POST，仅用户明确要求时；复用 `plan/confirm` 框架，不落库）。
2. `confirm` 分派注册表 + `write_ops` 按域拆分（纯重构，无行为变化）。
3. 图表升级（ECharts 或继续自绘 SVG，需先定依赖策略）。
4. 批量操作扩展：批量改期 / 批量改状态（非 complete）。
5. 前端组件拆分 + CSS 分文件；补前端单测（Vitest）。
6. 缩略图服务端缩放（需评估是否引入图像依赖，当前标准库无法做）。

### 6. 需要用户拍板的事项

- 是否引入 ECharts（新增前端依赖）还是保持零依赖自绘。
- 练练写回是否做、做到什么范围（只建训练计划 / 也改记录）。
- 是否需要给 serve 加最小鉴权（如启动时生成的本机 token），以便将来非回环访问。
- 前端是否引入 Vitest 测试框架。
- 是否 push `v1.66.0`–`v1.72.0` 这批 commit 与 tag 到远端（当前全部未 push）。

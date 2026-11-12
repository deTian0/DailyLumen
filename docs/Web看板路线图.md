# DailyLumen · Web 看板路线图

> **用途**：承载 Web 看板里程碑执行记录（立项时对应 PRD 第 8 节 W0→W11，其后扩至 W18 + 后续 B 项）。
> **权威顺序**：`docs/Web看板PRD.md`（要什么/为什么）→ 本文（按什么顺序做、做到哪了）。
> **不是**里程碑内容的重复定义——每条只记「做了什么、验收结果、commit/tag」。
> **立项基线**：`v1.60.0`；当时全量测试 1029 通过 / 2 跳过。
> **现行代码**：以 `pyproject.toml` 为准（采样 **v1.83.0**）；能力盘点见 [`能力图谱.md`](能力图谱.md)。

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
| W17 | 练练写回 | ✅ | `writes/keepstrong.py` 6 动作（set-weight/log-body/schedule/create-template/replace-template-actions/plan-command）入 `plan/confirm` 注册表（`needs=(env, ks_client)`，写回不落库、`db_changed=False`）；错误映射 5 类 + URLError；`routes_write` 加 6 条 `ks-*/plan` + `ks_client`；前端「训练」tab 加 `KeepStrongWrite` 卡（记体征体重 / 设下次重量，余 4 种留 CLI）；27 后端测试 | `v1.77.0`（未打 tag） |
| W18 | 视觉与信息呈现重做 | ✅ | 去新拟物 → 冷静青绿/石板灰扁平轻 elev；CLI 全文 → Markdown prose；分析图默认 1–2 主系列；指标卡语义色标；不改 API/业务 | `v1.78.0`（未打 tag） |

> 本表随每个里程碑完成实时更新；详细验收记录写在下方对应小节。
>
> **勘误（2026-11-09）**：W1–W18 的 commit 已推送到远端 `main`；W14–W18 标注的「未打 tag」仍属实（见后续待办 B10）。W18 之后已交付：v1.79 ClickUp 429+UI、v1.80 B2、v1.81 B3、v1.82 B4、v1.83 B15；另有 chore `274be6e` 增加 `.editorconfig`（钉 LF，未 bump 版本）。W17 行「余 4 种留 CLI」是当时快照；B4 / v1.82.0 已把剩余 4 动作接到面板。

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

### W17 — 练练写回（v1.77.0）

- **后端**：`api/writes/keepstrong.py` 6 动作入 W13 注册表（`@register(..., needs=("env", "ks_client"))`）：`ks_set_weight` / `ks_log_body` / `ks_schedule` / `ks_create_template` / `ks_replace_template_actions` / `ks_plan_command`。`plan_*` 只校验 + 出预览（零网络写），`_apply_*` 才调 `Client` 写方法（`user_confirmed=True`）。**写回不落库**：apply 返回 `db_changed=False`，不碰 `db_path` / `backup_dir`。错误映射：`CredError`→503 `credentials_missing`、`ApiKeyExpired`→401 `upstream_auth`、`SkillUpdateRequired`→426 `skill_update_required`、`RateLimited`→429 `rate_limited`、`KeepStrongError`→502 `writeback_failed`、`URLError`→504 `upstream_unreachable`。校验：`weight=0` 拒绝（空串=沿用历史）；id 走 `ID_RE`；`metric` ∈ {weight,fat,bodyRound}；`command` ∈ {delay,cancel_rest,add_alternative,add_temporary_workout}。中文 URL 编码由 `integrations.keepstrong.encode_query` 负责（已有测试覆盖）。
- **路由**：`routes_write.py` 加 6 条 `POST /api/write/ks-*/plan` + `ks_client` 注入 confirm；`build_router(..., ks_client=None)`（生产 `None` 时 apply 自建 `Client`）。门禁复用 W14 鉴权 + `--enable-write`。
- **前端**：`pages/Life.jsx`「训练」tab 下加 `KeepStrongWrite` 卡（`KsPreview` 列 preview 的 key/value，明示「写回不落库」）：记体征体重（metric/value/day/unit）+ 设下次重量（actionId/weight，空串=沿用历史）。排课 / 模板 / 计划命令需 actions JSON，留 CLI 并在卡里指明。`styles/content.css` 加 `.inline-form`。
- **测试**：`tests/api/test_write_w17.py` 27 例——6 动作 plan→confirm（预览不触网、confirm 才 POST、库字节不变）、校验（422）、错误映射（5 异常 + URLError）、路由（plan→confirm / 重放 409 / 422 / 503 / 401）。全用 `_FakeKS` 假 client，零网络。
- **验收**：`tests.api.test_write_w17` 27 例全绿；全量 Python 1241 通过 / 2 跳过；前端 6 文件 31 例；`npm run build` 通过；ruff 全绿。

---

### W18 — 视觉与信息呈现重做（v1.78.0）

- **范围**：只改 `web/src/styles/**` + 少量布局/呈现组件；**不改** API / 评分 / 归日 / 写操作语义；不引入大型 UI 库。
- **色板**：冷静青绿 `#0d7c6f` + 石板灰底；白表面 + 细边框 + 轻单阴影；去掉新拟物双阴影。
- **报告**：`lib/prose.js` + `Prose`；生活管家 / 体检 CLI 全文 → Markdown prose；周报等包进 `.prose-panel`。
- **图表**：trends ≥3 系列默认只显示前 2 条，图例可切换。
- **验收**：前端测试全绿；`npm run build`；全量 Python + ruff；截图 `local/screenshots/w18-visual/`。

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

1. ~~练练写回（POST，仅用户明确要求时；复用 `plan/confirm` 框架，不落库）~~ ✅ W17（v1.77.0）。
2. ~~`confirm` 分派注册表 + `write_ops` 按域拆分（纯重构，无行为变化）~~ ✅ W13（v1.73.0）。
3. ~~图表升级（ECharts 或继续自绘 SVG，需先定依赖策略）~~ ✅ W16（v1.76.0，ECharts）。
4. ~~补前端单测（Vitest）~~ ✅ W15（v1.75.0）。
5. ~~视觉与信息呈现重做（去新拟物 / prose 报告 / 图表降噪）~~ ✅ W18（v1.78.0）。
6. 批量操作扩展：批量改期 / 批量改状态（非 complete）。
7. 缩略图服务端缩放（需评估是否引入图像依赖，当前标准库无法做）。
8. 练练写回前端扩到排课 / 模板 / 计划命令（需 actions JSON 编辑器，当前留 CLI）。
   > **勘误（2026-11-09）**：已由 **B4 / v1.82.0** 完成（`KeepStrongWrite` + `ActionsJsonEditor`）。
9. W18 后续打磨：暗色模式、图表系列偏好记忆、doctor 结构化 JSON 视图、离线字体自托管。

### 6. 需要用户拍板的事项

- ~~是否引入 ECharts（新增前端依赖）还是保持零依赖自绘~~ → 已定 ECharts（W16）。
- ~~练练写回是否做、做到什么范围~~ → 已做 6 动作后端 + 2 常用前端入口（W17）。
- ~~是否需要给 serve 加最小鉴权~~ → 已加 `DAILYLUMEN_WEB_KEY`（W14）。
- ~~前端是否引入 Vitest 测试框架~~ → 已引入（W15）。
- 是否 push `v1.66.0`–`v1.78.0` 这批 commit 与 tag 到远端（当前全部未 push、未打 tag）。

> **勘误（2026-11-09 / B14）**：上条写于收口当时。其后 W1–W18 与 v1.79–v1.83 的 commit 均已推送 `main`；**仍不推 tag**（远端 tag 最新约 `v1.60.0`，补打事宜见 B10）。本条保留原文，只追加说明。

---

## 二期收口：W14–W17（v1.74.0–v1.77.0）

> 本节追加于 W17 提交后，作为 Web 生活管家面板二期收口记录。

### 1. 完成情况

| 里程碑 | 内容 | commit | 测试增量 |
| --- | --- | --- | --- |
| W14 | serve 最小鉴权（`DAILYLUMEN_WEB_KEY` + Bearer/X-DailyLumen-Key + 登录页） | `89fbdc3` | +17 后端 |
| W15 | 前端 Vitest 单测（api/route/todos/WriteFlow/Login） | `6f70a8e` | +24 前端 |
| W16 | ECharts 自绘图（`/api/charts/{kind}.json` 同源 + 前端 EChart/chartOption） | `c089493` | +6 后端 / +7 前端 |
| W17 | 练练写回（6 动作入 plan/confirm 注册表，写回不落库） | `ed0dec2` | +27 后端 |

全量 Python 1241 通过 / 2 跳过；前端 6 文件 31 例；ruff 全绿；`npm run build` 通过。**未打 tag、未 push**（按约定）。

> **勘误（2026-11-09 / B14）**：上句「未 push」已过时——对应 commit 其后已在 `main`；「未打 tag」仍属实（见 B10）。

### 2. 红线复核

- **R1 单源**：W16 `chart_series` 复用 `reports.chart.fetch_*_series` / `core.body.moving_average` / `config.BODY_TARGETS`，对拍测试锁住 JSON == SVG 源；W17 复用 `integrations.keepstrong.Client` 写方法，不另算口径。
- **R2 不破**：W17 写回不落库（`db_changed=False`），`exercise_min` 仍是健康分唯一运动输入，未触碰。
- **R3 分区**：W17 不碰 `habit_logs` / `personal_tracks`。
- **四层架构**：W16/W17 新代码全在 `api/`（queries / writes）与 `web/`，架构守卫全绿。
- **依赖收敛**：W16 新增 `echarts@5.6.0`（前端运行时依赖，钉版本）；W17 零新增 Python 依赖。
- **写盘安全**：W17 apply 不写库、不写 md，无回读需求；token 一次性（重放 409 已测）。

### 3. 已知问题 / 风险

- W16 bundle 283 KB → 1.31 MB（gzip 427 KB），ECharts 是首个前端运行时依赖；后续若要瘦身可改按需引入 echarts 模块。
- W17 前端只开「记体征体重 / 设下次重量」两个入口；排课 / 模板 / 计划命令需 actions JSON，仍走 CLI（卡里已指明）。
- W17 写回是外部副作用，无回读校验（练练 API 不提供读回端点）；以 `verify_*_response` 比对返回体为准，失败如实报 502。
- W14 鉴权仅本机回环 + 单 key；非回环访问需用户自行评估（README 已告警）。
- 全部 commit 未 push、未打 tag，待用户拍板。

> **勘误（2026-11-09 / B14）**：上条「未 push」已过时（commit 已推 `main`）；tag 仍待拍板（B10）。原文保留。

### 4. 截图

`local/screenshots/w14-w17/`：`w14-login.png`（登录页）、`w16-echarts-trends.png`（四维趋势 ECharts）、`w17-keepstrong-form.png`（练练写回表单）、`w17-keepstrong-preview.png`（记体征预览，零网络）。

---

## 后续待办（W18 之后）

> 追加于 2026-11-06；**状态对齐 2026-11-12**（代码版本 **v1.92.0**；B5–B8 / B16–**B19** 已合入，B8 纯文档不 bump；**B12 用户跳过**；**B13 用户确认不做**）。W1–W18 与 v1.79–v1.92 推远端 `main`（不推 tag；v1.92 待用户确认后推）。
> 下面每项独立做：一项一个 commit，**不打 tag**；写操作一律只用 mock / 临时库测试。
> **B 项总览**：B1 关闭/不修；B2✅ v1.80；B3✅ v1.81；B4✅ v1.82；B15✅ v1.83；**B5✅ v1.84**；**B7✅ v1.85**；**B6✅ v1.86**；**B8✅ 文档**；**B16✅ v1.88**；**B17✅ v1.89**；**B18✅ v1.90**；**B11✅ v1.91**；**B19✅ v1.92**；**B12 跳过/不做**；**B13 关闭/不做**；B9 运维提醒（非代码，Key 自检已通过）；B10 tag 不补打；B14 文档勘误✅。
> **下阶段指针** → [`日用闭环路线图.md`](日用闭环路线图.md)（**D1–D7**；产品阶段，勿再把日用闭环写成 B23+）。
> 本表剩余：B9 运维备忘；B20–B22 仍为 B19 明确不做的可选打磨（非当前主线）。

### 本轮已完成（B19 样式可访问性，2026-11-12）

- **B19 主题可访问性与样式 token 收敛（v1.92.0）**：对比度（`--on-accent` / `--on-status` / `--accent-ink`）、搜索框焦点、`var(--ink)` 无效引用、图表系列色跟主题、45 条死 token 清理、输入框文字/占位符/自动填充跨主题可读。计划见 [`plans/B19-样式可访问性与token收敛-plan.md`](plans/B19-样式可访问性与token收敛-plan.md)。
- **验收**：前端 17 文件 94 例全绿（新增 `tokens.test.js` 三主题 16 组对比度 + 未定义变量 + 硬编码色断言、`chartTheme.test.js` 映射色 ≥3:1 + 回退）；`npm run build` 重建 dist（CSS 31.63 KB）；Python 全量 1271 OK / 2 skip；ruff 全绿。**调色定稿**（2026-11-12）：用户实机 light 多页截图确认满意，B19 色板冻结，不再微调。

### 本轮已完成（B11 三套主题，2026-11-11）

- **B11 三套主题（v1.91.0）**：`light`（现有青绿）/ `dark` / `omni`（TokenClock/OmniClock 气质浅色皮：电蓝 + 浅灰 + 大圆角）；侧栏与登录页手动切换；`prefers-color-scheme` 仅默认 light/dark；ECharts chrome 跟主题。截图可放 `local/screenshots/v191-themes/`（gitignore 区）。
- **B13**：用户拍板**不做**缩略图服务端缩放（不引图像依赖）。

### 已完成（B18 OmniClock 风格渐变壳，2026-11-11）

- **B18 OmniClock 风格渐变壳（v1.90.0）**：视觉参考 OmniClock（非代码拷贝）；青绿/薄荷 mesh + 大圆角白卡 + 轻阴影 + 淡色图标底；侧栏轻毛玻璃；保留 B17 唯一主栏滚动。截图见 `local/screenshots/v190-omni-style/`（gitignore 区）。

### 已完成（B17 壳层唯一滚动，2026-11-10）

- **B17 壳层唯一滚动 / 去双滚动条（v1.89.0）**：`html/body/#root/.app` `overflow:hidden` + `100dvh`；仅 `.main` 纵向滚；去掉 `.prose-panel` / `.well` 的 max-height 内滚；窄屏侧栏顶栏后 main 仍唯一滚动。截图见 `local/screenshots/v189-scroll/`（gitignore 区）。

### 已完成（B16 视觉结构打磨，2026-11-10）

- **B16 视觉结构打磨（v1.88.0）**：状态点「点 + 短标签」收口；今日筛选/刷新贴待办区；空状态「说明 + 可选 ghost CTA」；主次按钮纪律（确认写操作仍 primary）。不换品牌色、不做默认暗色。

### 已完成（B8 文档，2026-11-09）

- **B8 写操作真机验收清单**：[`docs/Web看板写操作验收清单.md`](Web看板写操作验收清单.md)；对照 17 条 `writes` 注册表核实副作用；agent 不真机确认。

### 已完成（v1.86.0，2026-11-09）

- **B6 体检页结构化视图**：`summarize`（reports）+ `DoctorOut.summary`；前端卡片对齐 `is_healthy` / `render`；原文折叠保留。

### 已完成（v1.85.0，2026-11-09）

- **B7 周报 ASCII 条 → CSS 进度条**：`asciiBar` + `markdown.jsx` 表细胞；真实格式 = `_md_bar` 的 `█`/`░`；可选兼容 CLI `[█·]`；`role=progressbar` + aria；CLI/md 不改。

### 已完成（v1.84.0，2026-11-09）

- **B5 图表图例开关偏好记忆**：`legendPrefs` + `EChart` `legendselectchanged`；key 带 `v1`；系列键集合变更自动失效；Vitest 覆盖合法/损坏/变更/写失败。

### 已完成（v1.83.0，2026-11-09）

- **B15 练练完成后受控代勾 ClickUp「练练健身」**：CLI `clickup-habit --habit lianlian`（默认 dry-run / `--apply|--yes`）；写动作 `clickup_habit` 入 plan→confirm；只写 ClickUp、**不**写 `habit_logs` / `training_*`；练练 `completed` 仅旁证；Life 习惯/训练页入口；全 mock 测。

### 已完成（v1.82.0，2026-11-09）

- **B4 练练写回剩余 4 动作上面板**：`ks_schedule` / `ks_create_template` / `ks_replace_template_actions` / `ks_plan_command` 接到 `KeepStrongWrite`；`ActionsJsonEditor` 前端校验；Vitest mock 覆盖 plan→confirm / 422 / 401 `upstream_auth`；`api.js` 区分看板 401 与练练 `upstream_auth`。

### 已完成（v1.81.0，2026-11-09）

- **B3 ECharts 按需引入**：`EChart.jsx` 改 `echarts/core` + 按需注册；主 JS `1317.84→819.17 KB`（gzip `428.63→268.63 KB`）；无 dataZoom 故未注册。

### 已完成（v1.80.0，2026-11-09）

- **B2 字体本地化（方案 B）**：去掉 Google Fonts；`--font` / `--font-mono` 改系统栈；`test_web_dist` 断言 dist 无 `fonts.googleapis.com` / `fonts.gstatic.com`。

### 已完成（v1.79.0，2026-11-09）

- **ClickUp 429 限流**：`http_get` 有上限重试；耗尽后 API 映射 `rate_limited`，今日路由回退缓存；前端 `errText` 提示。
- **UI 交互打磨**：toast 贴顶、步骤卡不再竖排、主区独立滚动、`aria-busy` 转圈、分析图刻度/图例可读性。
- **明确不做（当时）**：B1 不修；不开 B2–B14。截图见 `local/screenshots/v179-ui/`（gitignore 区）。

### B1（关闭 / 不修）分析页四维趋势图「断线」

- **状态**：⛔ **关闭 / 不修**（2026-11-09 用户确认）。
- **理由**：排查后库→API→`chartOption`→ECharts SSR 各层均可画到最新日；用户确认所见「断点」来自**数据空值**（若干日期四维分为空 + `connectNulls: false`），不是代码缺陷。W18 默认图例只开前 2 系列也可能造成「只剩两条线」的观感。
- **当时现象备忘**：有人观感线到约 09-15 断开；只读核对 09-15 之后四维分无缺值。前段（约 07-16～08-28）确有空值断点。
- **涉及（备查，不再改）**：`queries.chart_series` / `reports.chart.fetch_series` / `GET /api/charts/{kind}.json` / `chartOption.js` / `EChart.jsx`。
- **若日后再议**：先目视确认是空值断点还是图例关闭，再决定是否做 B5（图例偏好）或改 `connectNulls`；R1 单源仍适用。

### B2（P1）字体本地化 ✅ v1.80.0

- **目标**：页面**零外网请求**。原 `web/index.html` 从 Google Fonts 加载 IBM Plex Sans / IBM Plex Mono / Noto Sans SC。
- **拍板**：方案 **B** 系统字体栈（零体积、零外网）；不做 A 自托管 woff2。
- **实现**：`web/index.html` 去掉 Google Fonts；`tokens.css` 的 `--font` = `system-ui, "Segoe UI", "Microsoft YaHei", "PingFang SC", sans-serif`，`--font-mono` = `ui-monospace, "Cascadia Code", …`；`test_web_dist.test_bundle_has_no_google_fonts`；`npm run build` 后 dist 入库。
- **验收**：dist 中不含 `fonts.googleapis.com` / `fonts.gstatic.com`；全量 Python + 前端测试 + ruff 全绿。

### B3（P1）ECharts 按需引入 ✅ v1.81.0

- **目标**：bundle 从约 1.31 MB（gzip 427 KB）瘦身。
- **涉及**：`web/src/components/EChart.jsx` 改成 `echarts/core` + 按需注册 `LineChart` / `BarChart`、`GridComponent` / `TooltipComponent` / `LegendComponent` / `MarkAreaComponent` / `MarkLineComponent`、`SVGRenderer`（`chartOption` 无 dataZoom，未注册）。
- **验收**：主 JS `1317.84→819.17 KB`（gzip `428.63→268.63 KB`）；`chartOption.test.js` 全绿；注册表对照 option 字段（line/bar/grid/tooltip/legend/markArea/markLine）。
- **风险**：漏注册组件会**静默**少画东西（比如目标带 markArea），四个 kind 都要逐个目视。

### B4（P1）练练写回剩余 4 个动作上面板 ✅ v1.82.0

- **目标**：把 `ks_schedule` / `ks_create_template` / `ks_replace_template_actions` / `ks_plan_command` 接到前端，沿用 `WriteFlow` 的预览→确认流程。
- **实现**：`KeepStrongWrite.jsx`（自 `Life.jsx` 抽出）+ `ActionsJsonEditor.jsx`；`WriteFlow` 增 `canPreview`；`api.js` 401 仅 `unauthorized` 清 key；文案明示「写回不落库、不可撤销」；`command` 下拉仅 4 值；前端不重复 URL 编码。
- **验收**：JSON 编辑器前端校验（语法 / 必填 `actionId`）+ 后端 422 回显；Vitest mock 覆盖 plan→confirm、422、401 `upstream_auth`；不连真练练；后端写路由未改。

### B15（P1）练练完成后受控代勾 ClickUp「练练健身」 ✅ v1.83.0

- **目标**：用户 / agent 显式触发，预览→确认后代勾 ClickUp 习惯 `lianlian`；习惯 Continuity 以 ClickUp 为主，训练事实仍以练练为准。
- **实现**：`pipeline/clickup_habit.py` + CLI `clickup-habit`；`writes/clickup.py` 登记 `clickup_habit`；Life 习惯/训练页 `ClickupHabitWrite`；只写 ClickUp（`db_changed=False`），**不**写 `habit_logs` / `training_*` / 四维分；练练 `completed` 旁证不强制；缺任务 / 401 / 429 结构化错误。
- **验收**：CLI/API 全 mock（dry-run / complete / 幂等 / 缺任务 / 上游错误）；Vitest mock plan→confirm；不对真 ClickUp 确认；`habit_logs` 仍走 `habits --sync`。
- **红线**：R3 不混 `personal_tracks`；禁止静默自动勾；禁止 ClickUp 反推训练表。

### B5（P2）图表系列开关偏好记忆 ✅ v1.84.0

- **目标**：图例开关按 kind 记到 localStorage，刷新后保持。
- **涉及**：`web/src/lib/legendPrefs.js`、`chartOption.js::defaultLegendSelected`、`EChart.jsx`（监听 `legendselectchanged`）。
- **验收**：Vitest：有偏好时覆盖默认（前 2 条），没有偏好或系列变了时回退默认；损坏的 JSON 不报错。
- **实现**：key=`dailylumen.legend.<kind>.v1`；键集合校验 + 版本号；防抖 300ms 保存。

### B6（P2）体检页结构化视图 ✅ v1.86.0

- **目标**：体检页基于 doctor 的**结构化结果**渲染（分项状态 / 计数 / 建议），不再 prose 全文直出。
- **涉及**：`reports/doctor.py::summarize`、`api/queries.doctor` / `DoctorOut.summary`、`web/src/pages/Doctor.jsx`。
- **验收**：对拍：`summarize` 与 `is_healthy` / `render` 结论一致；前端分项卡片 + 「查看原文」折叠。
- **实现**：六闸 `affects_health` 对齐 `is_healthy`；建议性分项不进健康结论；api 只透传。

### B7（P2）周报表格 ASCII 条改 CSS 进度条 ✅ v1.85.0

- **目标**：周报里的 ASCII 条（如 `████░░`）在 Web 端渲染成 CSS 进度条。
- **涉及**：`web/src/lib/asciiBar.js`、`markdown.jsx` 表细胞 / 行内、`web/src/styles/content.css`。CLI / md 输出保持不变。
- **验收**：Vitest：识别 `_md_bar` 的 `█`/`░` → `role="progressbar"`；含分数时 aria 取分数；不认识的格式原样显示。
- **勘误**：早期计划写「只改 prose.js」**不正确**——周报是 Markdown 表格，入口是 `markdown.jsx`（prose 仅 CLI 风格全文转 md）。
- **风险**：解析只在前端做，**不改后端报告文本**。

### B8（P2）写操作真机验收清单 ✅（纯文档，不 bump）

- **目标**：整理一份写操作真机验收清单，用户本人按清单逐项手动点（agent 不执行真实确认）。
- **文档**：[`docs/Web看板写操作验收清单.md`](Web看板写操作验收清单.md)（17 动作全覆盖；对照 `api/writes` 核实）。
- **验收**：前置 / 步骤 / 预期 / 回滚齐全；特例：`clickup_habit` 不写 `habit_logs`；练练 6 动作不落库。
- **定稿副作用表**（与注册表一致；定稿**不**自动写库，ingest 另项）：

| 动作 | 写远端 | 写库 `local/reviews.db` | 写 md / 文件 |
| --- | --- | --- | --- |
| task_create / task_status / task_batch | ✅ ClickUp | — | — |
| habits_sync | 读 ClickUp | ✅ `habit_logs` | — |
| ai_draft / finalize | — | — | ✅ 复盘 md |
| ingest | — | ✅ | — |
| clickup_pull | 读 ClickUp | ✅ `clickup_done` | — |
| vision | （LLM） | — | ✅ 复盘 md |
| inbox_archive | — | — | ✅ 移动收件箱 |
| ks_* ×6 | ✅ 练练 | ❌ 不落库 | — |
| clickup_habit | ✅ ClickUp | ❌ 不写 `habit_logs` | — |

### B9（运维提醒 · 非代码项）练练 API Key

- **性质**：运维提醒，**不是**代码里程碑；不改仓库、不 bump 版本。
- **现象（曾观测）**：练练接口返回 401 `apiKeyExpired` → CLI/面板可能静默无训练数据并走离线兜底。
- **处置**：在练练 App 重新生成 Key → 写入 `local/.env` 的 `KEEPSTRONG_API_KEY`（只改这一行，写完回读校验键名存在即可）。
- **约束**：只提醒，**不读、不打印 `.env` 的值**。B4 / B15 等测试走 mock，不依赖真 Key。
- **现状（2026-11-09）**：是否已换新 Key **以本机 `local/.env` 为准**（文档不跟踪密钥内容）；换完后用 `keepstrong --date <D> --stdout` 自检，不应再出现 `apiKeyExpired`。

### B10（已定调：不补打）版本 tag 补打

> **2026-11-09 用户定调**：tag 一律不补打、不推，agent 不再跟进此项（历史 tag 保持原样）。
> 以下原文保留作背景。

- **代码已推、tag 未齐**：v1.73.0–v1.83.1（含 EditorConfig chore）本地多半未打或未推 tag。
- **另**：本地曾有的 v1.60.1、v1.61.0–v1.72.0 等 tag **多数未推远端**（远端 tag 最新仍约 `v1.60.0`）。
- 等后续优化稳定后，由用户决定：统一补打并推，还是只打里程碑版本。在那之前 push 一律不带 `--tags`，也不开 `push.followTags`。

### B16（P2）视觉结构打磨 ✅ v1.88.0

- **目标**：借鉴参考图的「结构与节奏」，不换 W18 青绿品牌皮、不做默认暗色。
- **实现**：
  1. 状态点体系：`.dot-*` / `.status` / soft `pill-*`；doctor / 习惯 / 系统集成统一「点 + 短标签」。
  2. 列表筛选贴表：今日 `list-toolbar`；tabs / toolbar 收紧贴数据区。
  3. 空状态模板：`Empty` = 一句说明 + 可选 ghost CTA。
  4. 主次按钮：一屏/一卡尽量一个 primary；写操作确认保留 primary。
- **明确不做**：暗色（B11）、换 accent 蓝、多页签、玻璃拟态、3D 图标。
- **验收**：Vitest + `npm run build`；四处版本对齐；不打 tag。

### B17（P2）壳层唯一滚动 / 去双滚动条 ✅ v1.89.0

- **目标**：消灭浏览器级（html/body）滚动条；长内容只在 `.main` 一条滚；禁止与 `.prose-panel` 叠双条。
- **根因**：仅设 `.app { height:100vh }` 不够——grid 子项默认 `min-height:auto` 会按内容撑破壳，同时 `.prose-panel { max-height:70vh; overflow:auto }` 再叠内滚。
- **实现**：
  1. `tokens.css`：`html, body, #root { height:100%; overflow:hidden }`
  2. `layout.css`：`.app` 锁 `100dvh` + `minmax(0,1fr)`；侧栏 `min-height:0` 不滚；`.main` `overflow-y:auto` + `scrollbar-gutter:stable` + 细/hover 滚动条
  3. `content.css`：`.prose-panel` 去 max-height 内滚，报告全文流式跟随主栏
  4. `cards.css`：`.well` 去 `max-height:420px` 内滚（今日双栏随主栏）
  5. `login.css`：无壳时 `.login-wrap` 作唯一滚动
  6. 窄屏：`grid-template-rows: auto minmax(0,1fr)`，body 仍不滚
- **明确不做**：换品牌色、暗色、为 prose 保留第二套纵向滚动。
- **验收**：复盘页截图无浏览器条；Vitest + build；四处版本对齐；不打 tag。

### B18（P2）OmniClock 风格渐变壳 ✅ v1.90.0

- **目标**：把 OmniClock「柔和 mesh / 大圆角白卡 / 轻阴影 / 淡色图标底」气质落到 DailyLumen Web 看板；**视觉参考，非代码拷贝**。
- **实现**：
  1. `tokens.css`：青绿薄荷 mesh（`body::before` fixed）；半径 / 阴影 / 边框 / accent 略提亮；保留 B17 overflow 锁
  2. `layout.css`：侧栏 `backdrop-filter` 轻毛玻璃；导航 `.ico` 淡青绿底；按钮跟新半径
  3. `cards.css` / `login.css`：更大圆角与更轻 elev；登录卡 `--radius-lg`
  4. `content.css` / `feedback.css` / `tasks.css`：seg 胶囊轨、banner/toast/chart-well 协调
- **明确不做**：整站紫粉；企业宝蓝实心侧栏；回退 B17 双滚动；拷贝 OmniClock 源码进仓。
- **验收**：Vitest + build；截图今日/复盘；四处版本对齐；不打 tag。

### B11（可选）暗色模式 → 扩展为三套主题 ✅ v1.91.0

- **目标**：`prefers-color-scheme` 加手动切换，色板走 CSS 变量；扩展为三套主题。
- **三套**：
  1. `light` — 现有青绿薄荷（W18–B18）
  2. `dark` — 暗色
  3. `omni` — OmniClock/TokenClock 气质浅色皮（电蓝 accent、浅灰底、大圆角、软阴影、胶囊轨）；视觉参考，非源码拷贝
- **涉及**：`web/src/styles/tokens.css`（`[data-theme]`）、`themePrefs.js` / `ThemeContext` / `ThemeSwitcher`、`chartOption.js`、登录页与侧栏。
- **默认规则**：无 localStorage 时系统偏好只映射 light/dark；`omni` 仅显式选择；记忆 key `dailylumen.theme.v1`。
- **验收**：三套切换截图；Vitest 偏好/默认/损坏；对比度人工过一眼（完整 WCAG 不强制）。

### B19（P1）主题可访问性与样式 token 收敛 ✅ v1.92.0

- **目标**：三套主题正文 ≥ 4.5:1、图形/UI 边界 ≥ 3:1；所有 `var(--x)` 有定义；图表系列色跟主题。
- **实测问题**：dark `--on-accent` 白字仅 1.86:1；`.rstep-done` 约 1.4:1；搜索框焦点被 `outline:0` 压掉；`var(--ink)` 未定义；dark 图表学习/系统色低于 3:1。
- **实现**：
  1. `light` / `dark` / `omni` 分别定义 `--on-accent`、`--on-status`；新增 `--accent-strong`（实心控件）与 `--accent-ink`（文字）。
  2. omni `--muted` → `#6e6e73`；light/omni `--ink-amber` → `#8a5a00`；新增 `--border-input`。
  3. `.search:has(input:focus-visible)` 焦点环；`var(--ink)` → `var(--text)`；合并重复 `.visually-hidden`。
  4. 新增 `chartTheme.js`，按 series `key` 映射主题可访问色，未知 key 回退。
  5. 删除 `--chart-*` / `--blue|green|red|amber` / `--shadow-out|in` 共 45 条零引用声明；补 `--radius-2xs` / `--radius-xs`。
  6. 表单控件统一 `color: var(--text)`、`::placeholder`、`::selection`、`:-webkit-autofill`。
- **测试**：`tokens.test.js`（三主题对比度 + 未定义变量）、`chartTheme.test.js`（图表色 ≥3:1）、`chartOption.test.js` 更新。
- **明确不做**：B20 阅读/移动端、B21 视觉回归、B22 跟随系统、后端 SVG/JSON 改色、换品牌青绿、打 tag。

### B12–B14（补充，依据见各条）

- **B12 批量操作扩展**（批量改期 / 批量改状态，非 complete）：~~依据是本文「收口 §5 第 6 条」。~~ **⛔ 用户跳过 / 不做**（2026-11-12：无强需求；日用闭环走 D 系列，不在此重开批量写）。
- **B13 缩略图服务端缩放**：~~依据是「收口 §5 第 7 条」和「§4 已知问题」（每次读原图）；标准库做不了，要先拍板要不要引图像依赖。~~ **关闭 / 不做**（2026-11-11 用户确认：不引图像依赖、不实现缩放）。
- **B14 收口文档状态更新** ✅（2026-11-09 文档同步）：已在「收口 §6」「二期收口」测试总结与 §3 末条下**追加勘误**（不改写历史原文）；tag 问题仍见 B10。另同步 B1 关闭理由、B2–B4/B15 完成态、B 项总览与 `.editorconfig` 附注。

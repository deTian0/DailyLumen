# DailyLumen · Web 看板 PRD

> **用途**：把「Web 看板」从需求（`Web看板需求文档.md` v0.2）推进到**可拆里程碑的 PRD**：目标、前置工程项、详细功能清单、接口映射、验收、拆分建议。
> **立项基线**：`v1.60.0`（2026-11-05；全量测试当时 1029 通过 / 2 跳过）。
> **执行状态（2026-11-09）**：W0–W18 ✅ 已落地；后续 B 项与代码版本见 [`Web看板路线图.md`](Web看板路线图.md)（采样时 **v1.83.0**）。本文保留 PRD 原文，**不再**当「尚未开工」清单。
> **编号约定**：功能编号**沿用** `Web看板需求文档.md` 的 `FR-*`，本文不另起一套；前置工程项用 `PRE-*`；接口用 `API-*`。
> **不在本文**：具体实现步骤、视觉稿。里程碑执行记录在 `docs/Web看板路线图.md`，**不要**追加到已收口的旧路线图（M* / 深用期等）。

---

## 1. 目标

### 1.1 一句话目标

在浏览器里**查看并操作**现有 DailyLumen 能力（今日待办 / 日周月报 / 体征训练营养 / 分析图 / doctor / AI 预览），**逻辑与 CLI 同源**，本机随用随启。

### 1.2 成功标准（可验收）

| # | 标准 | 判定方式 |
| --- | --- | --- |
| G1 | 不配 DeepSeek，仅 `serve` 即可：刷今日待办/已办、读本周周报、读本月月报、看 stats、看一张 chart、看 doctor | P0 验收脚本 / 手测清单 |
| G2 | 同一输入下，Web 与 CLI 的数字（分数、周月均值、归日结果）逐项一致 | 对拍测试（见 PRE-05） |
| G3 | 任何写远端 / 写库 / 写 md 的操作必须二次确认，并回显等价 CLI 意图 | P2 验收 |
| G4 | 密钥不出现在任何 API 响应、前端 bundle、日志 | 自动化扫描 + 手测 |
| G5 | 引入 Web 后，现有 1029 测试不红，CLI 行为与输出不变 | 全量测试 |

### 1.3 非目标

第二套评分/归日实现；只写库不写 md；公网/多用户/OAuth；定时自动刷新；前端直连 DeepSeek；开启 `FEATURES["new_day"]`；视觉高保真阻塞需求。

---

## 2. 项目体检结论（本次实际核对）

### 2.1 已确认

| 项 | 结果 |
| --- | --- |
| 测试 | `unittest discover` 1029 个，OK，skipped=2 |
| 版本对齐 | `pyproject.toml` = `review_tool/__init__.py` = README 头 = 1.60.0；设计说明变更日志未逐条核对 |
| Web 代码 | `web/`、`review_tool/api/` **都不存在**；仅有需求文档 + 设计草案 + `docs/prototypes/` |
| TODO/FIXME | 全仓无堆积（grep 无命中） |
| 超大文件 | `reports/analyze.py` 1319 行、`reports/doctor.py` 1203、`storage/db.py` 1097；暂无需处理，但 Web 抽取编排时会碰到前两者 |
| 解释器 | miniconda Python 3.14.6；已装 `pydantic` / `pydantic-settings`，且已装 `fastapi 0.141.1` / `uvicorn 0.52.4`（**但 `pyproject.toml` 未声明**） |

### 2.2 未能确认 / 需你本机处理

| 项 | 情况 |
| --- | --- |
| ruff | 本机 PATH 与 `python -m ruff` 都没有，**lint 未验证**；DoD 要求 ruff 干净，需先装到工具环境 |
| 5 个显示 `M` 的文件 | `git status` 显示已修改，但 `git diff`、`--stat`、`--raw`、`--ignore-all-space` 全为空；`git update-index --refresh` 后仍显示。**原因未查明**（我此前推测为行尾属性刷新，没有证据）。这 5 个文件涉及 ClickUp 与配置测试，开工前建议先搞清楚，**不要**直接 `checkout` 清掉 |
| 报告函数签名 | 只核对了函数签名（grep），没有逐个读实现；下文“可复用”均指**存在同名入口**，是否零改动可调需在 PRE-02 逐个确认 |

---

## 3. 前置工程项（Web 开工前必须先解决）

这些是体检里发现的、会直接卡住 Web 的点。每项都应作为里程碑里的明确任务，而不是实现时顺手改。

| ID | 问题 | 为什么重要 | 建议做法 |
| --- | --- | --- | --- |
| **PRE-01** | 架构守卫不认识新层：`test_architecture.py` 的 `LAYERS` 只有 core/storage/integrations/pipeline/reports，`review_tool/api/` 会被当成 `root`（**不受限**） | 守卫静默失效，api 层可以随意反向依赖而测试仍绿 | 把 `api` 加入 `LAYERS`，`ALLOWED["api"]` = 可依赖其余全部层；其余层**不得**依赖 api；补对应守卫用例 |
| **PRE-02** | 多数 report 只有 `main(argv)` 打印，无可复用的“返回数据”入口（已见 `collect`+`render` 的：body/coach/habits/nutrition/tutor/steward/promises/stats/correlate/week_done/clickup_done；`finalize`、`day_help` 仅 `main`；`doctor` 只确认到 `render(result)`，其产出 `result` 的函数名未核） | API 要调用而不是 `subprocess` 跑 CLI（后者会造出第二套输出语义） | 逐个确认入口；缺的把编排抽到 pipeline/reports 共享函数，CLI 与 API 同调；**CLI 输出必须字节级不变**（现有测试守住） |
| **PRE-03** | pydantic 禁区：`test_business_layers_forbid_pydantic_and_dotenv` 禁止 `settings.py` 之外出现 pydantic*；FastAPI 的请求/响应模型天然用 pydantic | 直接写 FastAPI 会让该测试红；规则 2 也要求依赖收敛 | **需你拍板**：(a) 允许 `api/` 例外并修改守卫与规则 2 文案；(b) api 层只用 dataclass/dict，不声明 pydantic 模型。推荐 (a)，范围限定在 `review_tool/api/` |
| **PRE-04** | `fastapi`/`uvicorn` 未在 `pyproject.toml` 声明；NFR-3 要求 optional extra | 他人/CI `pip install -e .` 后 `serve` 起不来 | 新增 `[project.optional-dependencies] web = [...]`，版本**钉死**；`serve` 缺依赖时给出安装提示；CI 矩阵 3.10–3.13 需覆盖 |
| **PRE-05** | 缺少“Web 与 CLI 同源”的自动化证明 | G2 靠人眼不可持续 | 对拍测试：同一合成语料下，API 返回的数据与对应 `collect()`/`render()` 结果一致 |
| **PRE-06** | 周报入口按 `iso_week` 单参（`render_week_md(conn, iso_week)`）；而 `week_done.collect` 带 `year`。跨年周存在歧义风险 | Web 允许“切换周”，用户会点到跨年 | 核实现有行为；API 统一用 `year + iso_week`，若 CLI 不支持则只在 API 层前置校验，不改 CLI 口径 |
| **PRE-07** | `serve` 没有鉴权，监听端口后本机任意进程可读/可触发写（含 ClickUp 写回、DeepSeek 调用计费） | 本机单用户可接受，但必须显式化 | 默认绑 `127.0.0.1`；P2 写接口校验 `Origin`/`Host`（防 DNS rebinding 与浏览器跨站请求）并要求一次性确认 token；文档明示“无鉴权” |
| **PRE-08** | 写盘不可信（规则 3）、`.workbuddy/memory` append-only（规则 11）在 Web 写路径同样适用 | Web 的 P2 写 md 是新增写入口 | 所有 Web 写 md 复用现有写函数（已含回读校验的沿用，没有的补）；Web 不新增直接 `open(..., "w")` |
| **PRE-09** | 本机 lint 缺失（见 2.2） | DoD 要求 | 装 ruff 后跑一次，记录基线违规数，避免把存量问题算到 Web 头上 |
| **PRE-10** | 5 个 `M` 文件原因不明（见 2.2） | 影响“工作树干净”这条 DoD，也会污染 Web 首个 commit | 先查明再动工 |

---

## 4. 角色与场景

单一用户（本人），本机。典型场景：

1. 早上打开看板：今天待办/已办、昨日收工灯。
2. 复盘前：看昨日 `ai-context`、体征/训练/营养。
3. 周末/月末：读周报月报，复制或下载。
4. 想看趋势：stats / chart / correlate。
5. （DeepSeek mode）选一天点“AI 日总结”，先预览，再决定是否写草稿。
6. 出问题：看 doctor、fuse、集成最近错误。

---

## 5. 详细功能清单

**列说明**：`优先级`=P0/P1/P2；`数据来源`=现有入口（已见签名，PRE-02 前不保证零改动）；`验收`=最小可测标准。

### 5.1 A 外壳（P0）

| 编号 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- |
| FR-A1 | `python -m review_tool serve`：托管 `web/dist`，SPA fallback；缺 dist 返回明确提示页 | 新 `api/` | `GET /` | 无 dist 时提示“先 build / 使用入库 dist”；有 dist 时刷新任意前端路由不 404 |
| FR-A2 | 默认 `127.0.0.1`，端口可配（默认 8765）；监听非回环地址时启动打印警告 | Settings | — | 默认不可被局域网访问；改地址有警告 |
| FR-A3 | `serve` 缺 optional 依赖时友好退出 | PRE-04 | — | 提示 `pip install -e .[web]`，退出码非 0，不抛栈 |

### 5.2 B 总览（P0）

| 编号 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- |
| FR-B1 | 总览卡片：今日待办数 / 已办数 / mode / 三集成开关 / 收工灯 | ClickUp collect；`llm_mode`；`flags.is_enabled`；doctor | `GET /api/overview` | 集成关闭时卡片显示“未启用”而非报错 |
| FR-B2 | 一键“刷新今日” | 同 FR-C1/C2 | `POST /api/today/refresh` | 点击后更新数据与“上次刷新时间”；失败保留旧数据并提示 |

### 5.3 C ClickUp 查询

| 编号 | 优先级 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- | --- |
| FR-C1 | P0 | 今日待办（默认 日常+习惯+工作；含无 due；“仅今天 due”可选筛选） | `pipeline.clickup.collect` + `select_*`；`config.LIST_*` | `GET /api/today` | 与 CLI `clickup` 同日待办集合一致（对拍） |
| FR-C2 | P0 | 今日已办（含“次日早上补勾”回拨） | `select_completed`/`completion_day`/`rebate_target` | 同上 | 回拨样例日结果与 CLI 一致 |
| FR-C3 | P0 | 指定日期完成清单 | `reports.clickup_done.collect(start,end)` | `GET /api/clickup/done?date=` | 与 `clickup-done` 一致 |
| FR-C4 | P0 | 加载/空/失败态；失败信息不含密钥 | `integrations.last_error` | — | 401/超时/开关关各一种文案；响应与日志不含 key |
| FR-C5 | P1 | 素材日预览（`clickup` 只读面） | `pipeline.clickup.render/collect` | `GET /api/clickup/material?date=` | 与 `clickup --stdout` 同源 |
| FR-C6 | P1 | 任务外链打开 ClickUp | 任务 URL | — | 新标签打开，不在 Web 内写回 |
| FR-C7 | P1 | list 范围设置（孵化/年度是否入今日） | 配置 | `GET/PUT` 偏好（仅 UI 偏好，**不写 `local/.env` 的 list ID**） | 偏好存 `local/` 下缓存文件；不改 `LIST_*` 真值 |

### 5.4 D 健康查询（P1；P0 可先出 nutrition+body 其一）

| 编号 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- |
| FR-D1 | 体征 body：趋势数字/表 | `reports.body.collect` | `GET /api/body` | 与 `body --json` 一致 |
| FR-D2 | 运动 coach（含“离线兜底必须明示”，规则 14） | `reports.coach.collect(as_of)` | `GET /api/coach?date=` | 兜底来源时页面显式标注，不得写成“应为训练日” |
| FR-D3 | 习惯 habits；sync 先 dry-run 预览，确认后 apply | `reports.habits.collect`；`pipeline.habit_sync` | `GET /api/habits`；`POST /api/habits/sync`（P2） | `habit_logs` 与 `personal_tracks` 在 UI 分区展示，**永不合并** |
| FR-D4 | 营养 nutrition | `reports.nutrition.collect` | `GET /api/nutrition?date=` | 与 `nutrition --json` 一致 |

### 5.5 E 学习与督导（P1）

| 编号 | 功能 | 数据来源 | 接口 |
| --- | --- | --- | --- |
| FR-E1 | tutor | `reports.tutor.collect` | `GET /api/tutor?date=` |
| FR-E2 | promises（兑现口径：`unmapped`/`no_data` 不算未兑现，页面须分开展示） | `reports.promises.collect` | `GET /api/promises` |
| FR-E3 | steward 早/晚/周三视图 | `reports.steward.collect(...)` | `GET /api/steward?mode=morning\|evening\|week` |

验收：三者与对应 `--json`/文本输出同源；promises 页面不得把 `declined` 混入兑现率分母。

### 5.6 F 日周月报告

| 编号 | 优先级 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- | --- |
| FR-F1 | P0 | 周报在线展示，默认当前 ISO 周，可切周 | `analyze.render_week_md` | `GET /api/reports/week?year=&week=` | 与 `week <N>` 输出一致；跨年周见 PRE-06 |
| FR-F2 | P0 | 月报在线展示，默认当月，可切月 | `analyze.render_month_md` | `GET /api/reports/month?month=YYYYMM` | 与 `month <YYYYMM>` 一致 |
| FR-F3 | P0 | 日上下文 ai-context（只读） | `ai_review.build_context`/`render_markdown` | `GET /api/reports/ai-context?date=` | 与 `ai-context` 一致 |
| FR-F4 | P0 | 复制全文 / 下载 `.md` 或 json | 上述输出 | 响应头 `Content-Disposition` | 下载内容 = 页面内容 |
| FR-F5 | P1 | week-done“本周做成了什么” | `week_done.collect` | `GET /api/reports/week-done` | 与 `week-done` 一致 |
| FR-F6 | P1 | 月报 `--deep` 开关 | `monthly.build_month_deep` | `GET /api/reports/month?deep=1` | 与 `month --deep` 一致 |
| FR-F7 | P1 | 周/月报润色 `--polish` 预览（需 deepseek；先预览差分，**不默认写文件**） | `report_polish` | `POST /api/reports/polish/preview` | workbuddy mode 下禁用；预览不落盘 |

> 红线：周报/月报数字**一律现算**，不读取旧 md 里的数字（conventions §4）。Web 不得缓存跨口径变更的旧结果。

### 5.7 G 数据分析

| 编号 | 优先级 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- | --- |
| FR-G1 | P0 | stats 汇总 | `reports.stats.collect` | `GET /api/stats` | 与 `stats --json` 一致 |
| FR-G2 | P0 | chart：body/training/nutrition 可切换（首期直接嵌入现有 SVG） | `chart.build_*_chart` | `GET /api/charts/{kind}` | SVG 与 `chart` 命令产出一致；数据点数一致（NFR-5） |
| FR-G3 | P1 | correlate | `reports.correlate.collect` | `GET /api/correlate` | 样本不足时显示“样本不足”，不伪造相关系数 |
| FR-G4 | P1 | export 下载 csv/json | `pipeline.export` | `GET /api/export?format=` | 文件与 `export` 一致；**不暴露服务器任意路径** |
| FR-G5 | P1 | 前端自绘图（ECharts 等吃 json），替代嵌 SVG | `fetch_*_series` | `GET /api/charts/{kind}.json` | 数值与 SVG 同源（Q3） |

### 5.8 H / I AI（DeepSeek mode）

门禁：`DAILYLUMEN_LLM_MODE=deepseek` **且** DeepSeek 集成开启；否则按钮禁用并提示改用宿主/CLI（FR-H2）。

| 编号 | 优先级 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- | --- |
| FR-H1 | P1 | 选定日 → AI 日总结**预览**（不落盘） | `llm_review.run_llm_review`（dry-run） | `POST /api/ai/review/preview` | 预览期间不改 md/库；显示将调用的等价 CLI |
| FR-H2 | P1 | workbuddy mode 禁用与文案 | `llm_mode` | `GET /api/health` 携 mode | 禁用态按钮不可点，有说明 |
| FR-H3 | P2 | 写入“七-A AI 草稿”，二次确认，默认待人审 | `llm-review --write` 语义 | `POST /api/ai/review/write` | 写后回读校验；含待人审标记 |
| FR-H4 | P2 | 定稿 `llm-finalize`，写前并排 diff | `llm_finalize.run_llm_finalize` | `POST /api/ai/finalize` | 先 diff 再确认；与 CLI 同 |
| FR-I1 | P1 | 读图预览：上传 1..N 图 + 日期 + kind → 字段预览 | `vision_intake` / `llm_day` | `POST /api/ai/vision/preview`（multipart） | 限制大小与类型；临时文件用后清理；多图“后图覆盖”与 conflict 展示 |
| FR-I2 | P2 | 日流程写 md、归档收件箱，逐步确认 | `llm_day` / `inbox_archive` | `POST /api/ai/day/...` | **先落 md 再 ingest**（规则 9/13），不得只写库 |

### 5.9 J / K 写操作（P2，全部默认 dry-run + 显式确认）

| 编号 | 功能 | 数据来源 | 备注 |
| --- | --- | --- | --- |
| FR-J1 | ClickUp 建任务/改状态/评论 | `clickup_task` | 默认 dry-run，确认后 apply；回显等价 CLI |
| FR-J2 | clickup-push / keepstrong 写回 | 各 CLI | 练练写回须 `--yes` 语义；**写回不落库** |
| FR-K1 | 选择本地 md → ingest（可勾 allow-ai-draft） | `pipeline.ingest` | 路径必须限定在 `local/每日复盘/` 内，防路径穿越；注意 `ingest` 只处理首个路径参数（conventions §10.5）与绝对路径要求（§10.6） |
| FR-K2 | finalize / sync-docs / recompute-scores | 各 CLI | 强确认；recompute 必须先 dry-run，且提示“会改分数”；**不动 `local/reviews.db` 之前先备份**（规则 4） |
| FR-K3 | promise / three-things / improve-draft 生成预览与可选落盘 | 各 draft | 候选用户勾选后才落 md |

### 5.10 L 系统

| 编号 | 优先级 | 功能 | 数据来源 | 接口 | 验收 |
| --- | --- | --- | --- | --- | --- |
| FR-L1 | P0 | doctor 全文或结构化只读 | `reports.doctor`（PRE-02 先确认 collect 入口） | `GET /api/doctor` | 结论与 `is_healthy()` 一致；建议性项不当失败 |
| FR-L2 | P0 | health：版本 + 三集成开关 + mode | `__version__`；`flags` | `GET /api/health` | 不含任何密钥字段 |
| FR-L3 | P1 | fuse 只读；集成最近错误 | `reports.fuse`；`integrations.last_error` | `GET /api/fuse`；`GET /api/integrations/errors` | 有未失效绝对熔断时明示（对应 CLI rc=1 语义） |
| FR-L4 | P1 | day-help 步骤页（可复制命令） | `reports.day_help` | `GET /api/day-help` | 命令文本与 CLI 一致 |

### 5.11 不提供

`new-day`（开关刻意关闭）；任何定时任务；`import-history` 暂不出（待你决定）。

---

## 6. 非功能

| 编号 | 要求 | 备注 |
| --- | --- | --- |
| NFR-1 | 密钥永不下发 | 响应序列化白名单，不做“整对象直出” |
| NFR-2 | 默认回环地址 | 见 FR-A2 |
| NFR-3 | FastAPI/uvicorn 仅 optional extra | 见 PRE-04 |
| NFR-4 | 共享编排可单测；CLI 测试不红 | G5 |
| NFR-5 | 图表数据与 CLI 数值一致 | 对拍 |
| NFR-6 | 大报告分页/流式，避免卡死 | 先以实测最大周/月报体积为准再定 |
| NFR-7 | 文档：serve、build dist、开箱路径 | README + 独立部署文档同步 |
| NFR-8 | 写操作显示等价 CLI 意图 | P2 |
| NFR-9 | 并发：SQLite 单写者 | API 层写操作串行化；读用只读连接 |
| NFR-10 | 编码：Windows 控台 GBK 问题不影响 Web，但 API 一律 UTF-8 | — |
| NFR-11 | 前端依赖锁版本，`web/dist` 入库的构建可复现 | 记录 node 版本与 build 命令 |

---

## 7. 接口总表（草案）

只读：`/api/health` `/api/overview` `/api/today` `/api/clickup/done` `/api/clickup/material` `/api/reports/{week,month,ai-context,week-done}` `/api/stats` `/api/charts/{kind}` `/api/correlate` `/api/export` `/api/body` `/api/coach` `/api/habits` `/api/nutrition` `/api/tutor` `/api/promises` `/api/steward` `/api/doctor` `/api/fuse` `/api/integrations/errors` `/api/day-help`

预览（不落盘）：`/api/ai/review/preview` `/api/ai/vision/preview` `/api/reports/polish/preview`

写（P2，需确认 token）：`/api/today/refresh`（拉取，只读远端，视为读）、`/api/habits/sync` `/api/ai/review/write` `/api/ai/finalize` `/api/ai/day/*` `/api/clickup/task` `/api/ingest` `/api/maintenance/*`

统一约定：错误体 `{error: {code, message}}`，message 不含密钥与服务器绝对路径；日期参数统一 `YYYY-MM-DD`，周用 `year+week`，月用 `YYYYMM`。

---

## 8. 里程碑拆分建议

规则：**一次只做一个里程碑；一个 feature = 一处版本号 + 一个 commit + 一个 tag**；版本号四处对齐。下表建议写入 `docs/Web看板路线图.md`（需新建，不进旧路线图）。版本号只是示意，由实际发布顺序决定。

| 里程碑 | 内容 | 覆盖 | 依赖 | 完成判据 |
| --- | --- | --- | --- | --- |
| **W0** | 前置：PRE-03 拍板；PRE-09/10 清场；建路线图文档 | PRE-03/09/10 | 你的决定 | ruff 基线；工作树干净；路线图建立 |
| **W1** | `serve` 壳 + `health` + 架构守卫扩 `api` 层 + optional extra | FR-A1~A3、FR-L2、PRE-01/04/07 | W0 | 守卫能拦住 api 反向依赖；缺依赖提示友好；health 无密钥 |
| **W2** | 只读编排抽取与对拍框架（不加页面） | PRE-02/05/06 | W1 | 目标 report 均有可调入口；CLI 输出不变；对拍用例就位 |
| **W3** | ClickUp 今日 API（待办/已办/完成清单/错误态） | FR-B2、FR-C1~C4 | W2 | 对拍通过；回拨样例正确 |
| **W4** | 报告与分析 API（周/月/ai-context/stats/chart/doctor） | FR-F1~F4、FR-G1~G2、FR-L1 | W2 | G1 所需接口全齐 |
| **W5** | 前端脚手架 + P0 页面 + `web/dist` 入库 | FR-B1、P0 全部页面 | W3、W4 | **P0 验收（G1）**；README 开箱流程 |
| **W6** | 健康与学习督导查询（D、E） | FR-D1/D2/D4、FR-E1~E3 | W5 | 各页对拍 |
| **W7** | 报表增强（week-done / deep / correlate / export / fuse / day-help / 外链） | FR-F5/F6、FR-G3/G4、FR-L3/L4、FR-C5~C7 | W5 | P1 查询齐 |
| **W8** | AI 预览（review / vision / polish）+ mode 门禁 | FR-H1/H2/I1/F7 | W7 | 预览不落盘有测试证明 |
| **W9** | P2 写操作第一批：habits sync、AI 草稿写入、定稿 | FR-D3、FR-H3/H4 | W8、PRE-07/08 | 确认流 + 回读校验 + 回显 CLI |
| **W10** | P2 写操作第二批：读图日流程、ClickUp/练练写回、ingest/维护 | FR-I2、J、K | W9 | 路径白名单；dry-run 默认；备份先行 |
| **W11（可选）** | 前端自绘图（ECharts） | FR-G5 | W7 | 与 SVG 数值一致 |

拆分原则：先后端只读与对拍，再前端，最后才开写；W9/W10 可再细拆，每批不超过一个风险面（本地 md / 远端 ClickUp / 库维护分开）。

---

## 9. 待你拍板

| # | 问题 | 我的建议 | 阻塞 |
| --- | --- | --- | --- |
| D-1 | PRE-03：是否允许 `review_tool/api/` 使用 pydantic（FastAPI 模型）？ | 允许，仅限 `api/`；同步改守卫测试与规则 2 文案 | W1 |
| D-2 | 5 个 `M` 文件怎么处理（先查明还是先提交）？ | 先查明；若是你的有效改动，单独提交，不混入 Web | W0 |
| D-3 | P0 切片是否包含周报+月报+stats+一 chart+今日看板+doctor（需求文档 Q1）？ | 是；但按 W3/W4/W5 分三步交付，不要一口气 | W3–W5 |
| D-4 | AI 一键总结默认停在预览，写盘进 P2（Q2）？ | 是 | W8/W9 |
| D-5 | 图表首期嵌入现有 SVG，P1 后再换前端图（Q3）？ | 是 | W4 |
| D-6 | `import-history` 是否出 Web？ | 不出 | W10 |
| D-7 | 是否需要“关闭写接口”的总开关（只读模式启动）？ | 建议加 `serve --readonly` 默认开启，P2 写需显式 `--enable-write` | W1/W9 |
| D-8 | 设计草案里的 F1–F16 与需求文档 FR 编号并存，是否收口为只用 FR？ | 草案改为只指向本 PRD，避免双编号 | W0 |

---

## 10. 与其他文档的关系

| 文档 | 关系 |
| --- | --- |
| `Web看板需求文档.md` | 需求来源（v0.2）；FR 编号以它为准，本文补接口、验收、前置项、拆分 |
| `Web看板设计草案.md` | 形态备注；其 F* 编号建议废弃（D-8） |
| `集成能力路线图.md` | ClickUp/练练/DeepSeek 客户端已就绪，Web 消费 |
| `能力图谱.md` | Web 落地后回填“控制台”一层 |
| `docs/Web看板路线图.md` | **待建**，承载 W* 里程碑进度 |

---

## 11. 修订记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-11-05 | v0.1 | 基于项目体检与需求 v0.2 生成 PRD：目标、前置工程项、功能清单、接口、里程碑拆分建议 |

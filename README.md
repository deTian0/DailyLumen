# DailyLumen · 每日复盘系统

把每天的结构化复盘沉淀进 **SQLite 单一数据源**，再用脚本做周 / 月分析、体检与导出。  
业务逻辑基于 Python 标准库；配置层使用 **pydantic / pydantic-settings**（M46，默认读 `local/.env`）。

> 当前版本 **1.83.0**（B15：练练完成后受控代勾 ClickUp「练练健身」习惯）（历史：v1.82.0 Web 看板 B4：练练写回剩余 4 动作上面板；v1.81.0 Web 看板 B3：ECharts 按需引入；v1.80.0 Web 看板 B2：系统字体栈；v1.79.0 ClickUp 429 限流 + Web UI 交互打磨；v1.78.0 Web 看板 W18：视觉与信息呈现重做；v1.77.0 Web 看板 W17：练练写回；v1.76.0 Web 看板 W16：ECharts 自绘图；v1.75.0 Web 看板 W15：前端 Vitest 单测；v1.74.0 Web 看板 W14：serve 最小鉴权；v1.73.0 Web 看板 W13：写操作注册表 + 模块拆分；v1.72.0 Web 看板 W12：待办分组 / 批量完成 / 复盘进度条 / 门禁折叠 / 窄屏；v1.71.0 读图日流程 + 本周节奏快照空态；v1.70.0 ClickUp 建任务/改状态 + ingest 入口；v1.69.0 习惯同步 / AI 草稿写入 / 定稿；v1.68.0 AI 预览；v1.67.0 报表增强；v1.66.0 生活管家；v1.65.0 前端 P0 页面；v1.64.0 报告与分析 API；v1.63.0 ClickUp 今日 API；v1.62.0 只读编排与对拍；v1.61.0 serve 壳；v1.60.1 lint 基线清零；v1.60.0 集成能力 I1–I7；schema **v11**）｜测试数以全量跑为准
> · 规则与变更历史见 [`docs/设计说明.md`](docs/设计说明.md)｜**无 WorkBuddy 安装**见 [`docs/独立部署.md`](docs/独立部署.md)｜包级速查见 [`review_tool/README.md`](review_tool/README.md)

---

## 🖥️ Web 生活管家面板（开箱即用）

```bash
uv sync --extra web                          # 首次：装 fastapi / uvicorn（版本钉在 uv.lock）
# 首次：在 local/.env 末尾加一行访问密钥（未配置时 serve 拒绝启动）
#   DAILYLUMEN_WEB_KEY=<python -c "import secrets; print(secrets.token_urlsafe(32))" 的输出>
uv run python -m review_tool serve            # → http://127.0.0.1:8765/ ，登录页输入同一个密钥
```

- 前端构建产物 `web/dist` **已入库**，不需要 node 也能直接用；改了 `web/src` 才需要 `cd web; npm ci; npm run build` 重新构建。
- 前端单测（W15，Vitest + jsdom + Testing Library，版本钉在 `web/package-lock.json`）：`cd web; npm ci; npm test`（= `vitest run`，一次性跑完退出；开发时可 `npx vitest` 监听模式）。测试文件与源码同目录 `*.test.js(x)`，覆盖 `lib/api.js`（带 key / 401）、`lib/route.js`、`lib/todos.js`（待办分组）、`lib/chartOption.js`（W16 ECharts option）、`WriteFlow`（预览 → 确认 → 失败重试会重新预览）、登录页；全部 mock `fetch`，不连真服务。
- 分析页图表（W16）：前端用 **ECharts** 吃 `/api/charts/{kind}.json`（与 CLI `chart` 的 SVG **同源**——复用 `reports.chart.fetch_*_series` / `core.body.moving_average` / `config.BODY_TARGETS`，R1 单源），替代一期嵌 SVG；旧 SVG 端点 `/api/charts/{kind}` 保留供 CLI 与外部嵌入。
- 练练写回（W17 / B4）：生活管家「训练」tab 下六种写回（记体征 / 设下次重量 / 排课 / 创建模板 / 替换模板动作 / 计划命令）均复用 `plan/confirm`（写回**不落库、不可撤销、不作系统状态**，仅用户明确要求时）；actions JSON 前端校验 + 后端 422 回显。
- 代勾习惯（B15 / v1.83）：CLI `clickup-habit --habit lianlian`（默认 dry-run）与 Web `clickup_habit` 预览→确认；只勾 ClickUp「练练健身」，**不**写 `habit_logs` / 训练表（≠ 训练入库）。
- 页面：今日看板（待办 / 已办 / 收工灯 / 本周节奏 / 负荷）、复盘与报告（周报 / 月报 / 昨日上下文，可下载 .md）、生活管家（一日三步 / 晨间简报 / 夜间复盘指引 / 本周做成 / 连续天数 / 体征 / 训练 / 营养 / 习惯 / 学习 / 承诺兑现 / 跨维关联）、分析（stats + 图表）、体检（doctor / fuse / 集成失败）。
- 🔑 **最小鉴权（W14）**：所有 `/api/*` 需请求头带密钥（`Authorization: Bearer <key>` 或 `X-DailyLumen-Key`）；`/api/ping` 是不含信息的存活探针。密钥默认只存浏览器 sessionStorage（关标签页即失效），登录页勾选「记住」才存 localStorage；任何 401 自动回登录页。仍默认只绑 `127.0.0.1` 且只读；写接口需 `--enable-write`。HTTP 明文传输，别把 `--host` 改成局域网地址。
- 逻辑与 CLI 同源（`week` / `month` / `stats` / `doctor` / `clickup`），详见 `docs/Web看板PRD.md`、`docs/Web看板路线图.md`。

## 一日三步（心智模型）

日常只记三步——**先 md，再入库**；体脂可选、勿伪造。  
可执行清单（按当前 mode 给可复制命令）：`python -m review_tool day-help`

1. **投放收件箱** — 截图 / 简报放进 `local/每日复盘/收件箱/`（或口述给宿主）
2. **草稿** — `llm-day` / `llm-vision`（可 `--kind`；仅 deepseek）；或 WorkBuddy 宿主按 intake 手填
3. **定稿入库归档** — `llm-finalize --write` → `ingest` → `inbox-archive`（或 `llm-day --archive-inbox`）

有事看 `doctor`（收工摘要 +「今日能否收工」红绿灯）。健康叙事：**体重 + 饮食 + 睡眠 + 训练**。

---

## 目录结构

```
每日复盘计划/                         # 项目根 (仓库名 DailyLumen)
├── README.md                         # 本文件：项目说明 + 怎么用
├── review_tool/README.md             # 包级速查：模块地图 + CLI + 数据安全约定
├── pyproject.toml                    # 项目元数据 + pydantic* 依赖 + pytest / ruff
├── requirements.txt                  # 运行时依赖（pydantic / pydantic-settings）
├── 每日复盘模板.md                    # 空白模板（跟踪；无个人日记）
├── local/                            # 本机数据父目录（远程仅 .gitkeep + README）
│   ├── .env                          # 凭据（gitignore）
│   ├── reviews.db                    # 个人库（gitignore）
│   ├── exports/                      # 导出产物（gitignore）
│   └── 每日复盘/                     # 复盘 md / 收件箱截图 / 历史源（gitignore）
│       ├── 复盘/YYYY-MM/             # 标准复盘（ingest 扫描）
│       ├── 历史源复盘/               # 旧格式归档（不参与 ingest）
│       ├── 收件箱/                   # 手动投放截图 / 简报（不参与 ingest）
│       └── 草稿箱/                   # AI / 候选未定稿（不参与 ingest）
├── docs/                             # 设计说明.md + 独立部署.md + 迁移指南.md + 路线图…
│                                     #   + 集成能力路线图.md(I1–I7 ✅ v1.60) + 能力图谱.md
│                                     #   + 生活管家/运营期/深用期/隐私归一（历史留档）
├── tests/                            # 测试套件（标准库 unittest；需先 pip install -e .）
├── .github/workflows/ci.yml          # CI：多 Python 版本测试 + ruff 检查
├── .workbuddy/                       # 工作区配置（不参与运行；除 skills/ 外均不入 git）
│   ├── skills/                       # 项目级 skill（**已入 git**，方法资产跟代码一起版本化）
│   │   ├── dailylumen-conventions/   # 项目总纲：口径 / 权威归属 / 规约 / 工程约定 ★
│   │   ├── daily-review-intake/      # 素材 → 成品复盘（发截图 / 发文档 / 总结对话）★
│   │   ├── life-steward-daily/       # 总管家三段 SOP（晨间 / 夜间 / 周度）★
│   │   ├── doc-corpus-normalize/     # 文档批量标准化 SOP（可证明无损）
│   │   └── clickup-tracking/         # ClickUp 行为跟踪 ↔ 复盘衔接（结构 / 映射 / 口径）
│   ├── memory/                       # 本机日志 + 环境坑（不入 git，换机不迁移）
│   └── backup/                       # 迁移备份与一次性脚本（不入 git，换机不迁移）
└── review_tool/                      # 数据管道（标准 Python 包，四层架构：依赖只能自上而下）
    ├── __init__.py                   # 包公共 API（对外唯一契约，__all__）
    ├── __main__.py                   # 统一命令行入口 (python -m review_tool，纯路由)
    ├── config.py                     # ★ 可配置层：路径 + PROFILE / PERSONAL_ITEMS / HABITS / SCORE_THRESHOLDS / …
    ├── schema.sql                    # 建表语句（含 CHECK 约束）—— 与库文件同在包根
    ├── reviews.example.db            # 空库模板（新用户复制到 local/reviews.db）
    ├── core/                         # 领域层：零 I/O 纯规则（禁碰 SQLite / 文件系统）
    │   ├── util.py                   #   时间与数值转换、slug 生成
    │   ├── tracks.py                 #   打卡项归一化（自由文本 -> 规范 ID）★
    │   ├── bodyweight.py             #   徒手训练折算（描述动作 -> 运动时长）★
    │   ├── body.py                   #   体征纯规则（BMI / 均线 / 距目标）★
    │   ├── training.py               #   训练明细解析 + 合计 + 推荐规则纯函数 ★
    │   ├── habits.py                 #   行为习惯纯规则（归一化 / 依从率 / streak / 断更）★
    │   ├── nutrition.py              #   营养缺口 / 组合建议 / 极端值（零 I/O；与 ai_review 同源）★
    │   ├── learning.py               #   学习主题归一化 + 间隔重复队列推算（零 I/O）★
    │   ├── nutrition_items.py        #   食物明细附录解析 + 餐次归一化（零 I/O；v9 / M25）★
    │   └── score.py                  #   四维评分规则 ★
    ├── storage/                      # 持久化层：SQLite 的唯一出入口
    │   └── db.py                     #   读写 + 带版本增量迁移 + 打卡对账 + 体征 + 训练 + 习惯
    ├── pipeline/                     # 数据流转层：复盘 md <-> 库
    │   ├── parse.py                  #   解析 md -> 结构化 dict（体征侧车 + 训练明细）
    │   ├── ingest.py                 #   入库（体征 → body_metrics；训练 → 两表；R2 派生）
    │   ├── sync_docs.py              #   库中分数回写复盘 md（数据块 + 六章）★
    │   ├── import_history.py         #   语雀历史文件转换导入
    │   ├── new_day.py                #   生成当天文件（默认关闭，见 FEATURES）
    │   ├── clickup.py                #   ClickUp → 素材简报（--with-habits 可同步 habit_logs）★
    │   ├── habit_sync.py             #   ClickUp 习惯 → habit_logs（唯一 ClickUp→库写方向）★
    │   ├── clickup_sync.py           #   复盘入库 → 勾「每日复盘总结」（默认 dry-run）★
    │   └── export.py                 #   CSV / JSON 导出
    └── reports/                      # 产出层：读库生成面向人的结果
        ├── analyze.py                #   周 / 月分析（collect / render 分离，--json / --write）
        ├── body.py                   #   体征趋势（最新 / BMI / 7 日均 / 距目标）★
        ├── coach.py                  #   训练教练建议（达标 / 渐进 / 恢复 / 轮换）★
        ├── habits.py                 #   行为习惯依从率 / streak / 断更报告 ★
        ├── nutrition.py              #   营养缺口报告（FOOD_LIB 具体动作）★
        ├── tutor.py                  #   学习/复习报告（待复习 + 本周主题/投入/产出）★
        ├── steward.py                #   总管家编排（晨间 brief / 夜间指引 / 周度六段）★
        ├── streak.py                 #   正向连续天数（复盘 / 训练 / 打卡）
        ├── chart.py                  #   离线趋势 SVG（四维 / 体重 / 训练 / 热量双轴）★
        ├── correlate.py              #   跨维关联统计（样本门槛 + Pearson）★
        ├── doctor.py                 #   数据体检（对账 / R3 隔离 / 习惯断更 / 体征…）★
        ├── fuse.py                   #   熔断检测（低分双条件 + 相对基线偏离）★
        ├── ai_review.py              #   「七、AI 评价与建议」上下文构建器 ★
        └── recompute.py              #   按当前规则重算库中四维 / 系统分 ★
```

---


## 使用流程

所有命令统一通过包入口 `python -m review_tool` 运行，可在任意目录执行。  
加 `-h` 查看任意子命令的参数。

| 命令                                                   | 用途                                     |
| ---------------------------------------------------- | -------------------------------------- |
| `new-day [YYYY-MM-DD] [--force]`                     | 按模板生成当天文件 → `复盘/YYYY-MM/`（**默认关闭**）   |
| `ingest [路径.md] [--overwrite] [--prune-tracks] [--allow-ai-draft]` | 解析并入库（默认跳过含「草稿/待人审」的未定稿；`--allow-ai-draft` 强制） |
| `week [ISO周] [--json] [--write] [--polish]` / `month …` | 周 / 月分析；`--write` 落盘骨架；`--polish` 仅润色叙述（deepseek / R1）；`month --deep` 深评素材 |
| `week-done [ISO周] [--json]`                         | 本周做成了什么：ClickUp 完成 + 复盘三件事只读清单（FR-A4） |
| `ai-context [YYYY-MM-DD]`                            | 输出「七、AI 评价与建议」的确定性上下文                  |
| `llm-day --image PATH [--image …] --date D [--kind …] [--review] [--write] [--archive-inbox]` | 一键：多图 vision → 可选评价草稿（默认 dry-run；仅 deepseek；收工摘要） |
| `llm-review [YYYY-MM-DD] [--write]`                  | DeepSeek：ai-context → 写「七、AI」草稿（默认 dry-run；仅 mode=deepseek） |
| `llm-vision --image PATH --date D [--kind diet\|sleep\|screen] [--write]` | DeepSeek 读图 → md（分模板少串字段；体脂可选；不直写库） |
| `llm-finalize [YYYY-MM-DD] [--write]`                | 本地定稿：写前并排 diff（数据块+七、AI）；清 pending；七-A→七-B |
| `inbox-archive --date D --file PATH [--write]`       | 收件箱截图 → `已处理/日/`（优先移动；可还原） |
| `import-history [--check] [--src DIR]`               | 语雀历史文件转换为标准格式                          |
| `clickup [YYYY-MM-DD] [--out DIR] [--stdout] [--with-habits]` | 拉 ClickUp 当日素材；`--with-habits` 附习惯段并同步 `habit_logs` |
| `clickup-push [YYYY-MM-DD] [--apply]`                | 复盘已入库 → 勾 ClickUp「每日复盘总结」（**默认 dry-run**） |
| `clickup-habit --habit lianlian [--date D] [--apply]` | 受控代勾 ClickUp「练练健身」习惯（**默认 dry-run**；≠ 训练入库；不写 `habit_logs`） |
| `clickup-pull [--days N]`                            | ClickUp 已完成任务 → `clickup_done` 快照（会打网） |
| `clickup-done [YYYY-MM-DD]`                          | 某日 ClickUp 完成了什么（离线读快照，写复盘用） |
| `keepstrong [--date D] [--write] [--ingest] / --set-weight … --yes` | 练练读/落 md；写回须 `--yes` |
| `doctor`                                             | 数据体检 + 收工摘要 +「今日能否收工」红绿灯（缺字段/未定稿/未归档） |
| `day-help [YYYY-MM-DD] [--mode …]`                   | 一日三步 + workbuddy/deepseek 可复制命令模板 |
| `finalize [--date D] [--apply]`                      | 入库收尾：重算库分 + sync-docs 一键收口（默认 dry-run；≠ `llm-finalize`） |
| `promises [起始] [结束] [--json]`                    | 承诺对账：改进点 / 明日 Top 3 次日证据判定 |
| `body [--json]`                                      | 体征趋势：最新体重 / BMI / 7 日均 / 周变化 / 距目标 + **建议段**（M23，趋势×带位×外推） |
| `coach [YYYY-MM-DD] [--json]`                        | 训练教练建议：达标 / 渐进 / 恢复 / 部位轮换（每条带依据数字） |
| `habits [--json] [--sync [D [D]]]`                   | 行为习惯报告；`--sync` 支持单日 / 闭区间回填 → `habit_logs` |
| `daily-pull [--date D] [--apply]`                    | 夜间采集拉齐：练练落 md + 习惯快照 + 入库一条命令（dry-run 默认；**仅夜间**，会打网） |
| `promise-draft [--date D] [--stdout]`                | 明日 Top 3 候选草稿：ClickUp 到期任务 → 收件箱 md（草稿不入库，人勾选后回填） |
| `three-things-draft [--date D] [--stdout]`           | 今日三件事候选草稿：ClickUp 当日已完成 → 收件箱 md（与明日候选分文件，人勾 ≤3 回填） |
| `improve-draft [--date D] [--stdout] [--out DIR]`    | 改进点候选取数上下文（默认 stdout 零写盘；`--out` 落骨架；排序须走 life-decision-guide） |
| `nutrition [YYYY-MM-DD] [--json]`                    | 营养缺口：当日/近窗 vs macro_targets + FOOD_LIB 具体动作 |
| `tutor [YYYY-MM-DD] [--json]`                        | 学习/复习：今日待复习 + 本周主题/投入/产出物（独立指标区） |
| `steward --slot morning\|evening\|week […]`          | 总管家编排：晨间 brief / 夜间复盘指引 / 周度六段合一（只调用既有模块） |
| `fuse`                                               | 熔断检测：低分双条件（<6 且低于自身 28 日基线 ≥1 分）连续 3 天 + 相对基线偏离（长期低位不算熔断，退出码 0） |
| `sync-docs [--check]`                                | 把库里的四维分回写到复盘 md（数据块 + 六章表格）            |
| `recompute-scores [--apply]`                         | 按当前规则重算库中四维 / 系统分（默认只试算）               |
| `export [--format csv\|json] [--out DIR] [--stdout]` | 导出结构化数据                                |
| `stats [--json]`                                     | 一键统计：md 篇数 / 入库天数 / 打卡行 / 断更空洞（文档取数用） |
| `chart [--type body\|training\|nutrition\|all] [--out DIR] [--stdout]` | 离线 SVG：默认四维趋势；body/训练柱/热量双轴 |
| `correlate [--json] [--min-samples N]`               | 跨维关联（睡眠/训练/体重/热量/学习；样本不足 10 仅观察） |
| `version`                                            | 打印版本号                                  |

典型日常（复盘当晚）——对齐「一日三步」：

```bash
python -m review_tool day-help           # 按当前 mode 打印可复制命令
# 1. 投放：截图 → local/每日复盘/收件箱/；复制模板 → 复盘/YYYY-MM/YYYY-MM-DD.md
# 2. 草稿（deepseek 示例；workbuddy 则宿主按 intake 手填）
python -m review_tool llm-day --image 收件箱/….jpg --date YYYY-MM-DD --diff
python -m review_tool llm-day ... --date YYYY-MM-DD --write [--review]
# 3. 定稿 → 入库 → 归档
python -m review_tool llm-finalize YYYY-MM-DD --write   # 写前看并排 diff
python -m review_tool ingest …/YYYY-MM-DD.md
python -m review_tool inbox-archive --date YYYY-MM-DD --file … --write
python -m review_tool doctor             # 收工摘要 + 红绿灯
```

### 功能开关（`config.FEATURES`）

`python -m review_tool new-day`（按模板生成当天文件）**默认关闭** —— 手动复制模板更顺手，
故不参与日常流程。关闭状态下它会打印手动路径并返回退出码 2，**不写任何文件**；
命令本身仍在（`-h` 可读、`ROUTES` 未摘），打开只需改一处：

```python
# review_tool/config.py
FEATURES = {"new_day": True}   # 默认 False
```

`python -m review_tool`（无参数）会在被关闭的命令后标注「（已关闭）」。

### 集成开关（`config.INTEGRATIONS` / `local/.env`）

ClickUp / 练练健身 / DeepSeek 网关在 `review_tool/integrations/`；默认**开启**。
关掉后对应子命令明确报错、**不发网**（见 `.env.example` 的 `INTEGRATION_*_ENABLED`）。
DeepSeek 另须 `DAILYLUMEN_LLM_MODE=deepseek`。`doctor` / `day-help` 会提示集成状态。

### ⚠️ 入库的两种模式

`ingest` 默认是**保护模式**：源文件里为空的字段**不会**擦掉库里已有的值  
（防止「重跑一次 ingest 把已经攒下的数据清空」）。

确需用源文件真正清空某字段时，显式加 `--overwrite`：

```bash
python -m review_tool ingest --overwrite
```

### 运行测试

```bash
pip install -e .                               # 安装 pydantic*
python -m unittest discover -s tests -t .      # 见变更日志 / 全量跑测试数
```

覆盖：解析三种格式 / 打卡归一化 / 徒手训练折算 / 迁移幂等与表重建自愈 /  
upsert 防覆盖 / 训练日二态口径 / 评分边界 / 模板生成 / 体检 / 导出 /  
ClickUp 只读素材 + 回写通道 / 配置自洽 / 版本一致性 / **分层依赖方向（架构守卫）**。

---

## 数据块（通用数据入口）

复盘文件末尾的 ` ```data ` 代码块是**通用**数据入口，字段示例：

```data
日期: 2026-08-05
星期: 二
训练日: yes
睡眠时长_h: 6.42
睡眠质量: 84
入睡时间: 00:39
运动时长_min: 0
饮食热量_kcal: 1199
碳水_g: 150
脂肪_g: 40
蛋白质_g: 55
三餐情况: 早✓午✓晚✗
早餐按时: yes
手机屏幕_h: 10.9
深度工作_h: 0
学习投入_h: 1.5
生活投入_h: 2.0
健康分:
工作分:
学习分:
生活分:
一句话总结: ...
```

解析兼容三种格式：` ```data ` 代码块 / HTML 注释块 / 用户直接发的纯文本表头；  
按 `date` 主键 upsert，同一天重复入库会覆盖（保护模式下只补空）。

> **个人定制项（补剂 / 护肤）不在此数据块中**：它们由「一、日常打卡」勾选提取，  
> 归一化后落入 `personal_tracks` 表，不计入通用评分。详见下文「个人打卡归一化」。

---

## 🔖 个人打卡归一化（v1.3.0 新增）

**问题**：打卡项手写文本天然不稳定。改造前实测 244 条打卡记录里出现 **16 种文本形态**，  
实际只对应 6 个规范项——同一个 CoQ10 可能写成「CoQ10 ×1」「晨间-CoQ10 ×1 ＋ Exia 早3」  
「CoQ10 ×1 ＋ Exia 早3」…… 导致**依从率根本无法聚合**。

**方案**：打卡项定义收敛为 `config.PERSONAL_ITEMS` 单一来源，解析时归一化到规范 ID：

| 输入文本                           | 归一化结果                                 |
| ------------------------------ | ------------------------------------- |
| 「晨间」小节 + `CoQ10 ×1 ＋ Exia 早3`  | `coq10@morning`, `exia_am@morning`    |
| 「晚间」小节 + `Exia 晚3 ＋ Move Free` | `exia_pm@evening`, `movefree@evening` |
| 无小节 + `Move Free 红色 ×1`        | `movefree`（时段未知）                      |
| 任意位置 + `护肤`                    | `skincare`                            |

- `item_key` 规范项 ID（不含时段）—— **按它聚合依从率**
- `track_key` 规范项 ID + 时段后缀（`@morning` / `@noon` / `@evening`），时段未知则无后缀
- 未收录的新写法不会被丢弃：生成稳定的 `other:<slug>`，同样可聚合；  
  `doctor` 会把它列出来提示你补 alias

时段规则由 `PERSONAL_ITEMS` 的 `per_slot` 控制：  
`per_slot=True`（如 Move Free 午/晚都可能吃）跟随小节标题；`False`（如护肤）固定不分时段。

改造后实测：**16 种写法 → 6 个规范项，0 条未收敛**，依从率首次可算。

---


---

## 📐 设计与口径（已独立成册）

评分规则、口径定义、字段速查与变更日志已移到 **[`docs/设计说明.md`](docs/设计说明.md)**，
本文件只保留「怎么用」。涉及以下主题时请查设计说明：

| 想了解 | 去哪里 |
| --- | --- |
| 四维评分怎么算、档位阈值、熔断规则 | [设计说明 · 评分规则](docs/设计说明.md#-评分规则核心) |
| 分数的单一权威（库为准 / md 由库渲染） | [设计说明 · 分数的单一权威](docs/设计说明.md#-分数的单一权威v140) |
| 训练日达标、运动折算等统计口径 | [设计说明 · 统计口径](docs/设计说明.md#-统计口径v130v132-三轮收口) |
| **ClickUp 素材源**（只读管道 / 归日口径 / 不参与评分） | [设计说明 · ClickUp 素材源](docs/设计说明.md) |
| 数据库字段含义 | [设计说明 · 数据库字段速查](docs/设计说明.md#数据库字段速查) |
| 版本变更历史 | [设计说明 · 变更日志](docs/设计说明.md#变更日志) |
| **集成能力**（I1–I7 ✅） | [**集成能力路线图**](docs/集成能力路线图.md)（v1.60.0 收尾） |
| **历史里程碑**（M1–M8） | [**路线图**](docs/路线图.md)（已完成，勿追加） |
| **生活管家怎么做**（里程碑 **M9–M21** / 文件级范围 / DoD） | [**生活管家路线图**](docs/生活管家路线图.md)（已完成，历史留档） |
| **运营期做什么**（里程碑 **M22–M35**） | [**运营期路线图**](docs/运营期路线图.md)（已完成，勿追加） |
| **深用期 / 隐私归一**（M36–M50） | [深用期](docs/深用期路线图.md) · [隐私与配置归一](docs/隐私与配置归一路线图.md)（均已完成） |
| **生活管家升级要什么**（7 个角色 / FR / 数据需求 / 决策点） | [**生活管家需求文档**](docs/生活管家需求文档.md) |
| **现在真有什么能力**（能力矩阵 / 资产盘点 / 缺口） | [**能力图谱**](docs/能力图谱.md) |
| **项目口径总纲**（范围 / 权威归属 / 评分与熔断 / 规约 / 工程约定） | 项目级 skill `.workbuddy/skills/dailylumen-conventions/`（随 git 走） |
| **发我截图 / 文档，生成当天复盘** | 项目级 skill `.workbuddy/skills/daily-review-intake/`（按需加载，无需定时任务） |
| **某件人生事该不该做 / 值不值 / 犯不犯法** | 项目级 skill `.workbuddy/skills/life-decision-guide/`（按《高性价比人生指南》先查条目再答，见该目录 `README.md`） |
| **换一台电脑跑 / 重装后恢复** | [**迁移指南**](docs/迁移指南.md)（含「什么在 git / 什么搬 / 什么重建」与落地命令） |

## 🩺 数据体检（`doctor`）

一次性回答「数据还准不准、全不全、新不新」：

```bash
python -m review_tool doctor
```

| 检查项        | 说明                                     |
| ---------- | -------------------------------------- |
| 数据库        | schema 版本 / 记录数 / 完整性检查                |
| 新鲜度        | 最新复盘距今多少天，超过 1 天即提示补录                  |
| 历史断更       | 相邻入库日间隔 > 1 天的空洞（v1.7.1；建议性，不拦）         |
| 文件 ↔ 数据库对账 | 双向差集：哪些 md 没入库、哪些库中记录找不到源文件            |
| 旧格式归档      | 哪些天的数据源只存在于「历史源复盘」，建议先转换               |
| 数据完整度      | 核心字段缺失统计                               |
| 打卡归一化      | 是否还有未收敛到规范项的 `other:*` 记录              |
| 训练日口径      | 记录值与离线兜底约定不同的天数（v1.27.0 起：非故障，仅提示）     |
| 分数一致性      | 库中四维 / 系统分 vs「按字段重算」的结果（v1.4.1；提示性，不拦） |
| 打卡对账       | 库中打卡行能否在源 md 找到对应勾选（v1.4.2；提示性，不拦）     |
| 打卡依从率骤降   | 近 N 日完成率相对此前基线骤降（v1.10.1；建议性，不拦）      |
| 收件箱消化     | 素材按「日期是否已入库」分已消化 / 待处理（v1.33.2；留档不算待处理） |
| 熔断检测       | 单维度连续低分 + 相对基线漂移（v1.4.0；提示性，不拦）        |

退出码：健康 = 0，有待处理项 = 1（便于接入自动化）。

## 📤 导出（`export`）

```bash
python -m review_tool export                    # 3 个 CSV 到 exports/（utf-8-sig，Excel 直开）
python -m review_tool export --format json      # 单个 JSON
python -m review_tool export --stdout           # 打印到终端
```

导出三份数据：`daily_reviews`（每日通用字段）、`personal_tracks`（打卡明细）、  
`adherence`（**按规范项聚合的依从率**）。

---

## 🤖 AI 评价与建议（第七章）

每日复盘模板固定包含 `## 七、AI 评价与建议`，在数据回填后撰写（素材由用户手动投递，
流程见项目级 skill `daily-review-intake`；本项目**没有定时任务**）：

- **评价**：2–3 条，含「做得好」与「需留意」，必须引用当日与近 7 日的实际数字。
- **建议**：2–4 条可执行动作，带具体时间锚点或目标值。

撰写前先运行上下文构建器拿事实依据：

```bash
python -m review_tool ai-context 2026-09-15
```

输出三块内容（**全部来自读库与规则判定，不含模型生成**）：

1. **当日事实**：睡眠/饮食（含三大营养素）/屏幕/深度工作/学习/生活/四维分。
2. **近 7 日均值**：系统与四维、睡眠/屏幕/深度工作/饮食、宏量日均。
3. **规则命中的关注点**：按 `config.SCORE_THRESHOLDS` 阈值与  
   `config.PROFILE["macro_targets"]` 目标逐条判定。

关注点规则（均为客观陈述，不下结论）：

| 类别 | 触发条件                                              |
| -- | ------------------------------------------------- |
| 睡眠 | 时长 < 7h｜质量 < 80｜入睡落在熬夜档（00:00–06:00）或晚睡档（>23:30）  |
| 运动 | 训练日未记录（按口径记 0，v1.3.2：没填即没练）｜训练日运动 0 分钟            |
| 饮食 | kcal 出 1200–2200 区间；碳水/脂肪/蛋白低于 `macro_targets` 目标 |
| 屏幕 | > 10h                                             |
| 四维 | 工作/学习/生活分 ≤3（偏低；标尺 v2 起分值下限是 1，不再是 3）        |
| 趋势 | 连续 ≥3 天出现同一问题（入睡晚 / 学习分 ≤3 / 屏幕 >10h）             |

> **文案里的时间点也是从配置算出来的**：例如「未在 23:30 前」取自  
> `SCORE_THRESHOLDS["bedtime"]["ok_max"]`，改阈值文案会跟着变，不会出现  
> 「阈值改了、文案还在说老数字」。
>
> 该章节为**叙事文本**，不入 `daily_reviews` 表、不参与评分；评分仍由客观规则决定。

---


## 个人化配置（可配置层）

本项目对「个人差异」做了显式抽象，小伙伴拿到后**只需改 `review_tool/config.py` 四处**，  
无需碰模板与代码：

- **`PROFILE`**：作息窗口、三大营养素每日目标（`macro_targets`）、  
  训练日约定（`training_weekdays`，0=周一）。
- **`PERSONAL_ITEMS`**：个人打卡项定义（补剂 / 护肤 / 自定义），  
  每项含 `key` / `slot` / `per_slot` / `label` / `aliases`。  
  **这是解析与归一化的单一来源**，改这里即可适配自己的打卡方案。
- **`SCORE_THRESHOLDS`**：四维评分阈值与权重。默认值 = 当前用户的评分偏好；  
  同时驱动「AI 评价与建议」的关注点规则与文案。
- **`BODYWEIGHT_MOVES` / `BODYWEIGHT_RULES`**：徒手训练折算。每项含  
  `aliases` / `per_minute` / `set_rest_sec` / `default_reps`；  
  规则含单日上下限与次数合理性上限。**默认只启用俯卧撑**，  
  其他动作按同样结构追加一行即可。

`tests/settings/test_config.py` 会校验配置自洽性（权重与实现对应、alias 不互相抢匹配、  
阈值单调性、版本一致性），改错配置测试会直接报出来。

---

## 工作区配置（`.workbuddy/`）

`.workbuddy/` 存放工作区级配置与记忆，**不参与程序运行**：

- **`skills/`**（**已入 git**）：项目级 skill，属**方法资产** —— 跟代码一起版本化、打 tag。
  当前含六个：
  - `dailylumen-conventions` —— **项目口径总纲**（范围边界 / 权威归属 / 评分与熔断 /
    文档与库规约 / 工程约定 / 交付流程）。**跨会话要一直遵守的约定写在这里，而不写在
    `memory/`** —— 因为它随 `clone` 走，换机不丢。
  - `daily-review-intake` —— **素材 → 成品复盘流程**（发截图 / 发文档 / 总结对话时的
    日期归属、字段顺序、每晚投递清单 §0.5、评价与建议规格、格式规范）。**本项目已无定时任务**：
    素材由用户手动投递，靠这个 skill 按需生成复盘。
  - `life-steward-daily` —— **总管家三段 SOP**（晨间 brief / 夜间复盘指引 / 周度六段，
    对应 CLI `steward`）。
  - `doc-corpus-normalize` —— 批量文档标准化 SOP（保证解析 / 入库可证明无损）。
  - `clickup-tracking` —— **ClickUp 行为跟踪 ↔ 复盘衔接**（空间结构 / list ID / 映射口径 /
    按 `date_closed` 取当日完成项（含「次日早上补勾」回拨）/ 「两套打卡体系不许混」的边界）。取数**已代码化**：
    `python -m review_tool clickup [日期]` 直接产素材简报到 `收件箱/`（只读，不落库、
    不参与评分）；本 skill 讲的是空间结构与映射口径。
  - `life-decision-guide` —— **人生决策问答**（「该不该 / 值不值 / 怎么选 / 这样犯法吗」）：
    先去《高性价比人生指南》正文里查条目，再按钱 / 时间 / 毅力三项成本与证据等级排序回答，
    每条注明第几节第几条，查不到就说查不到。规则来自上游
    `github.com/eternity4719/HowToLiveBetter`，本仓库只保存其 `SKILL.md` 副本加三处本机补丁；
    装法 / 加载 / 升级见 [该目录的 `README.md`](.workbuddy/skills/life-decision-guide/README.md)。
    **纯只读**：不参与四维评分、不写 `reviews.db`。
  `.gitignore` 用 `.workbuddy/*` + `!.workbuddy/skills/` 开白名单；**注意必须写成
  `.workbuddy/*`**，写成 `.workbuddy/` 会连目录一起排除，白名单会静默失效。
- **`memory/`**（不入 git，**换机不迁移**）：本机会话执行日志（按日期）+ `MEMORY.md`。
  只放**本机专属**内容（写盘 / git 引用 / 缓存类环境坑）与 skill 加载指针 ——
  项目口径一律不写在这里，避免换机后丢失。开工前先读、做完后写回。
- **`backup/`**（不入 git，**换机不迁移**）：数据库迁移前备份、一次性脚本与 `archived/` 归档。

**人格与跨项目 SOP 不在本仓库**：
助手人格与协作准则已归到用户级记忆 `~/.workbuddy/MEMORY.md` 的「协作准则」段
（每会话无条件注入，机制上保证 always-on）；跨项目通用 SOP（`sqlite-safe-migration`
含「假装自己是 CI」自检、`nmpa-cosmetic-record`）在用户级 `~/.workbuddy/skills/`。
用户级资产的保管**不属本仓库职责**，本仓库只保证项目级 skill 随代码入库。

---


# DailyLumen · Web 看板需求文档

> **本文只写「要什么」**（模块 / FR / 边界 / 验收）。视觉高保真**曾暂缓**；W18 已交付扁平青绿视觉（见路线图）。  
> **「怎么做 / 做到哪了」** → [`Web看板路线图.md`](Web看板路线图.md)（W0–W18 ✅；后续 B 项）。  
> **立项基线**：`v1.60.0` ｜ 当时 CLI ≈ 38 子命令 ｜ 集成 ClickUp / 练练 / DeepSeek。  
> **执行状态（2026-11-09）**：主线已落地至代码 **v1.83.0**；本文保留需求原文作 FR 权威，不以「未做 Web」解读。  
> **需求草案**：**v0.2** · 2026-11-05 · 相对 v0.1 **大幅加宽范围**（查询 / 报表 / AI 总结 / 日周月报）。

---

## 0. 一页摘要

| 问题 | 答案 |
| --- | --- |
| 要解决什么 | 在浏览器里**操作与查看**现有系统能力：待办、体征/习惯/营养/训练、日/周/月报告、数据分析图、doctor；在 **DeepSeek mode** 下支持 **AI 一键总结** 等 |
| 怎么跑 | 本机单进程托管 `web/dist` + API；随用随启 |
| 和 CLI | **同一套业务逻辑**；页面 = UI；禁止第二套评分/归日/拉数实现 |
| 分期 | **P0 可看可刷** → **P1 全查询与报表** → **P2 谨慎写操作 / AI 写盘** |

**相对 v0.1 的纠正**：不只做「今日待办两栏」；**绝大多数现有只读能力都应有页面入口**；写操作与 AI 落盘按风险分期，但需求上要列全。

---

## 1. 定位与原则

### 1.1 定位

Web = **本机生活管家控制台**（查询 + 报表 + 有限操作），不是精简版 ClickUp，也不是丢掉 CLI。

| 层 | Web 角色 |
| --- | --- |
| 执行层 ClickUp / 练练 | 拉取展示；写回须确认（P2） |
| 源层 md | 展示路径/状态；写 md 仅走现有 llm-* / draft 语义（P1–P2） |
| 评价层 db + reports | **图表、周月报、stats、correlate 只读为主** |

### 1.2 原则

| ID | 原则 |
| --- | --- |
| P1 | **逻辑单源**：页面 / API 只调用现有 `pipeline` / `reports` / `integrations` |
| P2 | **CLI 行为不变**；Web 是超集入口，不是分叉实现 |
| P3 | **密钥不上前端** |
| P4 | **默认 localhost** |
| P5 | **G1**：写库仍应先 md 再 ingest；Web 不得提供「只写 db」捷径 |
| P6 | **不改四维权重**；报表数字与 CLI 同源 |
| P7 | **随用随启** |
| P8 | **mode 门禁**：DeepSeek 类按钮仅在 `DAILYLUMEN_LLM_MODE=deepseek` 且集成开时可用；workbuddy 下提示走宿主/CLI |

### 1.3 已拍板技术约束

Vite + React · `web/dist` 入库 · 新拟物方向（视觉后做）· `LIST_*` 归日沿用。

---

## 2. 信息架构（站点地图）

```
Web 控制台
├── 总览 Dashboard          今日摘要 / 收工灯 / 快捷刷新
├── 执行 · ClickUp
│   ├── 今日待办 / 已办
│   ├── 日完成清单（clickup-done）
│   ├── 素材预览（clickup 只读）
│   └── （P2）任务写回
├── 健康
│   ├── 体征 body
│   ├── 运动 coach
│   ├── 习惯 habits（含 sync 触发）
│   └── 营养 nutrition
├── 学习与督导
│   ├── 学习 tutor
│   ├── 承诺 promises
│   └── 管家 steward（早/晚/周）
├── 报告
│   ├── 日上下文 ai-context（只读）
│   ├── 周报 week / week-done
│   ├── 月报 month（含 deep）
│   └── （P1）报告润色 week|month --polish
├── 分析
│   ├── stats
│   ├── chart（body/training/nutrition）
│   ├── correlate
│   └── export 下载
├── AI（DeepSeek）
│   ├── 一键日总结（llm-review / 基于 ai-context）
│   ├── 读图入库助手（llm-vision / llm-day）说明 + 触发（文件上传）
│   └── 定稿 llm-finalize
├── 系统
│   ├── doctor / fuse 只读
│   ├── day-help
│   ├── 集成开关与最近错误（只读）
│   └── version / health
└── （P2）运维写：ingest 选文件、finalize --apply、sync-docs、recompute 等
```

---

## 3. 功能模块总表

| 模块 | 对应现有能力（CLI） | 页面能力概要 | 优先级 |
| --- | --- | --- | --- |
| **A 外壳** | （新）serve | 托管 dist、localhost、健康检查 | P0 |
| **B 总览** | doctor 摘要 + day-help 片段 | 卡片：待办数/已办数/收工灯/mode；一键刷新 ClickUp | P0 |
| **C ClickUp 查询** | clickup / clickup-done / clickup-pull 只读面 | 今日待办·已办、完成清单、按日查询 | P0 |
| **D 健康查询** | body / coach / habits / nutrition | 表格+关键指标；日期选择 | P0–P1 |
| **E 学习督导查询** | tutor / promises / steward | JSON/结构化卡片展示 | P1 |
| **F 日周月报告** | ai-context / week / week-done / month | 在线阅读、复制、下载 md/json | **P0（周月）/ P1（deep）** |
| **G 数据分析** | stats / chart / correlate / export | 图表页、相关分析、导出按钮 | **P0–P1** |
| **H AI 总结** | llm-review / ai-context；可选 --polish | **一键总结**、预览、（确认后）写草稿 | P1（预览）/ P2（写盘） |
| **I AI 读图日流程** | llm-vision / llm-day / finalize / inbox-archive | 上传图、dry-run 预览、写 md、定稿、归档 | P1–P2 |
| **J ClickUp/练练写** | clickup-task/push、keepstrong --yes、habits --sync | 表单 + 明确确认 | P2 |
| **K 复盘管线写** | ingest / finalize / sync-docs / recompute / drafts | 文件选择 + 确认；默认二次确认 | P2 |
| **L 系统** | doctor / fuse / version / 集成错误 | 体检全文、熔断只读、错误指引 | P0–P1 |

---

## 4. 分优先级需求（FR）

### 4.1 P0 · 必须能「看见」与「刷到」

| 编号 | 模块 | 需求 | 复用 |
| --- | --- | --- | --- |
| FR-A1 | A | serve + 挂载 dist + SPA fallback；缺 dist 有提示 | 新 API 壳 |
| FR-A2 | A | 默认 `127.0.0.1`；端口可配 | — |
| FR-B1 | B | 总览页：今日待办/已办计数、mode、ClickUp 开关、收工灯（若可廉价取） | doctor / 今日看板 API |
| FR-B2 | B | 总览「刷新今日」= 触发 ClickUp 今日重拉 | 同 C |
| FR-C1 | C | 今日待办列表（list 默认：日常+习惯+工作） | LIST_* + Client |
| FR-C2 | C | 今日已办列表（归日含回拨） | clickup-done 同源 |
| FR-C3 | C | 指定日期的完成清单查询 | clickup-done |
| FR-C4 | C | 加载/空/失败态；失败无密钥 | last_error 风格 |
| FR-F1 | F | **周报**在线展示（默认当前 ISO 周）；可切换周 | `week` |
| FR-F2 | F | **月报**在线展示（默认当月）；可切换月 | `month` |
| FR-F3 | F | **日上下文**（ai-context）只读展示选定日 | `ai-context` |
| FR-F4 | F | 报告支持复制全文 / 下载为 `.md` 或 json | reports 输出 |
| FR-G1 | G | **stats** 汇总页 | `stats` |
| FR-G2 | G | **chart** 至少 body / training / nutrition 一类可切换出图（图文件或前端绘图，数据同源） | `chart` |
| FR-L1 | L | doctor 全文或结构化区块只读 | `doctor` |
| FR-L2 | L | health：版本 + 三集成开关 + mode | Settings |

**P0 验收**：仅开 serve，不配 DeepSeek，也能：刷今日待办已办、读本周周报、读本月月报、看 stats/一张 chart、看 doctor。

### 4.2 P1 · 全查询铺开 + AI 预览 + 报表增强

| 编号 | 模块 | 需求 | 复用 |
| --- | --- | --- | --- |
| FR-D1 | D | 体征 body 页（趋势数字/表） | `body` |
| FR-D2 | D | 运动 coach 页 | `coach` |
| FR-D3 | D | 习惯 habits 页；按钮触发 sync（dry-run 预览 + 确认 apply） | `habits` |
| FR-D4 | D | 营养 nutrition 页 | `nutrition` |
| FR-E1 | E | tutor / promises / steward 三页只读 | 各 CLI |
| FR-C5 | C | clickup 素材日预览（stdout 同源结构化） | `clickup` |
| FR-C6 | C | 任务外链打开 ClickUp | URL |
| FR-F5 | F | week-done「本周做成了什么」 | `week-done` |
| FR-F6 | F | month `--deep` 深评开关 | `month --deep` |
| FR-F7 | F | **报告润色**：按钮调用 `--polish`（需 deepseek）；先预览差分再可选写文件 | `week/month --polish` |
| FR-G3 | G | correlate 页 | `correlate` |
| FR-G4 | G | export 一键下载 csv/json | `export` |
| FR-H1 | H | **AI 一键日总结**：选定日 → 调 llm-review **dry-run/预览** → 面板展示 | `llm-review` |
| FR-H2 | H | workbuddy mode 下 AI 按钮禁用 + 文案引导宿主/切 mode | llm_mode |
| FR-I1 | I | 读图：上传 1..N 图 + 日期 + kind → vision/day **预览**字段 | `llm-vision`/`llm-day` |
| FR-L3 | L | fuse 只读；integration 最近错误面板 | fuse / last_error |
| FR-L4 | L | day-help 步骤页（可复制命令） | `day-help` |

**P1 验收**：健康/学习查询齐；周月报可 deep/polish（deepseek 时）；AI 日总结可预览不强制写盘；读图可预览结构化字段。

### 4.3 P2 · 写操作与 AI 落盘（显式确认）

| 编号 | 模块 | 需求 | 复用 |
| --- | --- | --- | --- |
| FR-H3 | H | 总结「写入七、AI 草稿」须二次确认；默认仍待人审 | `llm-review --write` |
| FR-H4 | H | 定稿按钮 → llm-finalize | `llm-finalize` |
| FR-I2 | I | 读图/日流程写入 md、归档收件箱；逐步确认 | llm-day / inbox-archive |
| FR-J1 | J | clickup-task 建任务/改状态/评论；默认 dry-run，确认后 apply | `clickup-task` |
| FR-J2 | J | clickup-push / keepstrong 写类；`--yes`/`--apply` 语义上屏 | 各 CLI |
| FR-K1 | K | 选择本地 md → ingest（可勾 allow-ai-draft） | `ingest` |
| FR-K2 | K | finalize / sync-docs / recompute-scores 带强确认 | 各 CLI |
| FR-K3 | K | promise/three-things/improve-draft 生成预览与可选落盘 | drafts |

**P2 验收**：任一写操作无「点一下就改远端/改库」；均有确认与结果回显；失败可追踪。

---

## 5. ClickUp 今日口径（保持）

| List | 首期今日待办/已办 |
| --- | --- |
| LIST_DAILY / HABITS / WORK | ✅ |
| INCUBATOR / ANNUAL | 默认否，设置项 P1 可开 |

- 已办：归日 = 今天（含回拨）  
- 待办：纳入 list 的未完成（含无 due）；「仅今天 due」为可选筛选  

---

## 6. AI 能力（需求说明）

| 能力 | mode 要求 | 页面表现 |
| --- | --- | --- |
| 一键日总结 | deepseek + INTEGRATION_DEEPSEEK | 按钮 → 预览 →（P2）写草稿 |
| 周/月报润色 | 同上 | 在报告页「润色」→ 预览 |
| 读图结构化 | 同上 | 上传 → 预览字段 →（P2）写 md |
| workbuddy | — | 上述按钮禁用；提示用宿主对话或改 mode |

**不做**：前端直连 DeepSeek（绕过后端）；把 key 塞进浏览器。

---

## 7. 非功能（NFR）

| 编号 | 要求 |
| --- | --- |
| NFR-1 | 密钥永不下发前端 |
| NFR-2 | 默认只绑回环地址 |
| NFR-3 | FastAPI/uvicorn 等仅 API 层 optional extra |
| NFR-4 | 共享编排可单测；全量 CLI 测试不红 |
| NFR-5 | 图表数据与 CLI chart/stats 数值一致（允许渲染库不同） |
| NFR-6 | 大报告流式或分页，避免一次卡死浏览器 |
| NFR-7 | 文档：serve、build dist、开箱路径 |
| NFR-8 | 写操作审计：UI 必须显示将调用的等价 CLI 意图 |

---

## 8. 边界

### 8.1 依赖

全量现有 CLI 背后的 reports/pipeline/integrations；doctor；llm_*；Settings。

### 8.2 明确不做（全局）

| 不做 | 原因 |
| --- | --- |
| 第二套评分/归日 | 防漂移 |
| 只写 db 不写 md | 破 G1 |
| 公网多用户 OAuth | 个人本机 |
| 定时自动刷新挂机 | 项目无调度传统 |
| 视觉高保真阻塞需求 | 已暂缓原型 |

---

## 9. 与 CLI 对照清单（防漏）

| CLI | Web 模块 | 分期 |
| --- | --- | --- |
| day-help | L | P1 |
| doctor / fuse | L / B | P0–P1 |
| clickup / clickup-done / clickup-pull | C | P0–P1 |
| clickup-push / clickup-task | J | P2 |
| keepstrong | J / D 附属 | P1 读 / P2 写 |
| body / coach / habits / nutrition | D | P1（P0 可先做 nutrition+body 其一） |
| tutor / promises / steward | E | P1 |
| ai-context | F | P0 |
| week / week-done / month | F | P0 |
| week\|month --polish | F/H | P1 |
| stats / chart / correlate / export | G | P0–P1 |
| llm-review / vision / day / finalize | H/I | P1 预览 / P2 写 |
| inbox-archive | I | P2 |
| ingest / finalize / sync-docs / recompute / drafts | K | P2 |
| daily-pull | J/C | P2 |
| new-day | — | 保持关闭，Web 不提供 |
| import-history | K | P2 或不出 |
| version | L | P0 |

---

## 10. 待拍板

| # | 问题 | 建议 |
| --- | --- | --- |
| Q1 | P0 是否接受「周报+月报+stats+一 chart + 今日看板 + doctor」打包为第一可演示切片？ | 是 |
| Q2 | AI 一键总结默认停在**预览**，写盘进 P2？ | 是 |
| Q3 | 图表：后端出 png（现 chart）嵌入 vs 前端 ECharts 吃 json？ | 先嵌入现 chart，P1 可换前端图 |
| Q4 | 习惯 sync / ClickUp 写是否必须进第一年范围？ | 进 P2 即可 |
| Q5 | 默认端口 | `8765` |

---

## 11. 文档关系

| 文档 | 关系 |
| --- | --- |
| 本文 | **需求权威（v0.2 起加宽）** |
| Web看板设计草案.md | 技术形态备注；视觉原型非门禁 |
| 集成能力路线图.md | Client 已具备，Web 消费 |
| 能力图谱.md | 实现后回填「Web 控制台」一层 |

---

## 12. 修订记录

| 日期 | 版本 | 说明 |
| --- | --- | --- |
| 2026-11-05 | v0.1 | 仅今日待办窄范围 |
| 2026-11-05 | **v0.2** | 扩为全产品控制台：查询 / 日周月报 / 分析 / AI 总结分期 |

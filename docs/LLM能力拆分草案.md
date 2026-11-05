# LLM 能力拆分草案（已拍板 · 慢动手）

> **状态**：关键决策已拍板（§7）；**L-1 ✅（v1.53.0）**；**L-2 契约指针 ✅**；
> **L-3 评价草稿 ✅（v1.54.0 · `llm-review`）**；**读图 intake ✅（v1.54.0 · `llm-vision`）**；
> **可独立跑打磨 ✅（v1.55.0）**；**体脂可选 + llm-day ✅（v1.56.0）**；  
> **草稿/定稿守卫 + 独立部署专章 ✅（v1.56.1）**。  
> Vision 冒烟（合成 PNG + 可选 LIVE）已在 deepseek 客户端单测覆盖；真实图本机投放见下。  
> **日期**：2026-11-05｜**当前版本锚点**：v1.56.1  
> **动机**：把「永远本地可跑的静态能力」与「可选的 LLM / WorkBuddy 宿主能力」拆清，并为  
> WorkBuddy 上「读图填数 + 写评价建议」立一份可复用的标准契约；同时预留 **DeepSeek**  
> 模式，使仓库可独立部署、不依赖 WorkBuddy。

---

## 0. 调研结论（一句话）

**仓库内今天已有可选 DeepSeek 调用**（`pipeline/deepseek.py` + `llm-review` / `llm-vision`），  
默认仍是 **`workbuddy`**：不发模型请求，由宿主代劳。  
`reports/ai_review.py` 名带 AI，实为**确定性上下文构建器**（`ai-context`），**不调用任何模型**；  
L-3 在其之上可选调 DeepSeek 写 md 草稿。

因此拆分的核心是：

1. **固化边界**：哪些永远不依赖模型；  
2. **配置**：互斥 **mode**（`workbuddy` | `deepseek`）走现有 Settings 分层；  
3. **标准化 I/O 契约**：宿主与 DeepSeek **同一落点**（先 md 再 `ingest`）。

---

## 术语（通俗）

| 术语 | 通俗意思 |
| --- | --- |
| **默认 provider 语义** | 「空配置时，谁来干 LLM 的活？」——与互斥 **mode** 是**同一配置维度**，不是另开一套。空 / 未配时 = **`workbuddy`**（见下「workbuddy 模式说明」）。配成 `deepseek` 时改由仓库进程内调 DeepSeek API，承担全部 LLM。 |
| **契约落点** | 「宿主 / 适配层的 I/O 约定写在哪、谁引用？」——**正文**建议写在本草案（§4），或另建独立宿主契约短文；**intake skill** 只加指针，不另造第二套口径。字段映射表可附本文件附录或独立短文，供宿主与日后 deepseek 模式共用。 |

### workbuddy 模式说明（澄清 · 勿误读成 SDK）

**WorkBuddy 本身就是一个 Agent**，本仓库**没有**可供进程内 HTTP/SDK 调用的 WorkBuddy 模型接口。因此 **`mode=workbuddy` = 只能依赖 WorkBuddy 运行环境执行**：在对话 / 技能里由**宿主**读图、理解、填建议，产出**结构化数据**后按项目契约**写入复盘 md**，再 `ingest`——**不是**仓库去「调用 WorkBuddy API / provider SDK」。对比：`deepseek` 才是仓库进程内调外部 API；`workbuddy` 是宿主代劳后把结果落盘。

---

## 已拍板（2026-11-04）

1. **运行模式互斥，同时仅一种**  
   - 默认 **`workbuddy`**：依赖 WorkBuddy **宿主 Agent 运行时**（对话/技能）履约；**无**对外暴露的 WorkBuddy 模型 HTTP/SDK 供本仓库调用。宿主产出结构化数据 → 落复盘 md → `ingest`（见上「workbuddy 模式说明」）。  
   - 可选 **`deepseek`**：仓库**进程内**调 DeepSeek API，**承担全部 LLM**；目标可独立部署、不依赖 WorkBuddy。  
   - 目前外部提供方**仅 DeepSeek**（不预留 openai / anthropic 等并列 mode；也**不**存在 WorkBuddy provider SDK）。

2. **Key 按提供方分，不强行统一**  
   - 模式：`DAILYLUMEN_LLM_MODE=workbuddy|deepseek`（默认 `workbuddy`）。  
   - DeepSeek：`DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`（仅 deepseek 模式需要）。  
   - **workbuddy 模式不需要**上述 DeepSeek 键。  
   - ⛔ **不要**强行统一成 `DAILYLUMEN_LLM_API_KEY`。

3. **Vision / 评价调用**  
   - 首期曾拍「先契约 + mode」；**v1.54.0 已落地** deepseek 下的评价草稿与读图 intake。  
   - **v1.55.0** 多图 / 重试 / `--diff` / doctor 可观测 / 宿主短契约。  
   - **v1.56.0** `llm-day`；体脂可选；多图后图覆盖 + conflict；部分失败可恢复。  
   - workbuddy 模式继续由宿主按 intake / 契约做读图与写建议。

4. **红线不变**：任何 LLM / 宿主产出 → **先落 md 再 `ingest`**；禁止只进库不落 md。

---

## 1. 现状盘点

### 1.1 Static（永远本地 · 无模型）

| 层 / 模块 | 代表 | 备注 |
| --- | --- | --- |
| `core/*` | `score` / `nutrition` / `body` / `habits` / `training` / `tracks` / `promises` / `llm_contract` / `llm_mode` | 零 I/O 纯规则；测试与 `test_architecture` 强制分层 |
| `config.py` 业务规则 | `SCORE_THRESHOLDS` / `FOOD_LIB` / `FUSE_RULES` / `PERSONAL_ITEMS` / `HABITS` / `BODYWEIGHT_*` | D6=B / D7=B，留代码不进 `.env` |
| `storage` + `pipeline/ingest` / `parse` / `sync_docs` | md ↔ SQLite | 安全网：删库可从 md 重建 |
| `reports` 多数 | `doctor` / `fuse` / `analyze` / `body` / `coach` / `nutrition` / `steward` / `stats` / `correlate` / `ai_review`（上下文） | 读库 + 规则；`ai_review` **不含模型生成** |
| 外部 HTTP（非 LLM） | ClickUp / KeepStrong | 结构化 API；凭据在 `local/.env`；仍先落 md 再 ingest（G1） |

依赖面：`pyproject.toml` 运行时仅 `pydantic` + `pydantic-settings`。**无** `openai` / `anthropic` / DeepSeek SDK 等（DeepSeek 用标准库 urllib）。

### 1.2 宿主 LLM 与仓库 deepseek 适配（同一契约）

| 能力 | 载体 | 与本地解耦方式 |
| --- | --- | --- |
| 截图 → 数值 / 附录 | skill `daily-review-intake` + **`llm-host-contract`**；**deepseek**：`llm-vision`（可多图） | 宿主或 CLI → **只写 md** → `ingest` |
| 「七、AI 评价与建议」 | intake §4 + `ai-context`；**deepseek**：`llm-review`（`--diff`） | 本地出事实；措辞由宿主或 DeepSeek 草稿 → 人审 |
| 口述流水 / 改进点候选排序叙事 | intake §0.6 / §0.8 | 草稿落收件箱；人勾选后才进复盘 md |

### 1.3 配置扩展点（现成）

- **Settings**：`review_tool/settings.py`（pydantic-settings；默认读 `local/.env`）  
- **分层**：凭据 / 环境差异 / 个人参数 → `local/.env`；业务规则留代码  
- **模板**：`.env.example`（含 LLM / DeepSeek 段注释）  
- **功能开关先例**：`config.FEATURES`（目前仅 `new_day=False`，刻意不擅自打开）  
- **⛔ 不另引** `python-dotenv`  
- **运行摘要**：`local/llm_last_run.json`（gitignore；无密钥 / 无正文）

### 1.4 口径红线（方案必须继承）

- G1：截图 / API / LLM 产出 **都是输入通道**；先落 md 再 `ingest`；禁止只进库。  
- 「七、AI…」叙事权威在源 md；分数权威在库（`sync-docs`）。  
- 新表不参与四维评分；不改四维权重 / 不碰历史分。  
- `habit_logs` 与 `personal_tracks` 永不合并。  
- 无定时调度；素材手动投递。

---

## 2. 建议的能力分层

```
┌─────────────────────────────────────────────────────────────┐
│  L0 Static（永远本地）                                        │
│  core 评分 / FOOD_LIB / doctor / fuse / ingest / sync-docs   │
│  ClickUp·KeepStrong 拉数 → 落 md → ingest                    │
│  ai-context / body·coach·nutrition 等确定性建议              │
│  验收：mode=workbuddy 且无 DeepSeek key → 全量 unittest 仍绿 │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ 只读契约（事实块 / 关注点 / 草稿）
┌─────────────────────────────────────────────────────────────┐
│  L1 LLM-optional（互斥 mode；默认 workbuddy）                  │
│  workbuddy：仓库不发模型请求；由宿主履约（见 L2 / §4）          │
│  deepseek：仓库调 DeepSeek（chat + Vision）→ 只写 md 草稿      │
│  产出仍只能写 md / 收件箱，禁止直写库                           │
└─────────────────────────────────────────────────────────────┘
                              ▲
                              │ 同一套 I/O 契约（见 §4）
┌─────────────────────────────────────────────────────────────┐
│  L2 WorkBuddy-host（宿主能力 · 仓库外；mode=workbuddy）         │
│  读图填数据块 / 写「七、AI 评价与建议」/ 挂 life-decision-guide  │
│  标准化：输入素材清单 + 输出 md 落点 + 必跑 CLI 清单             │
│  与 deepseek 模式互换：同一契约，宿主实现或 DeepSeek 实现二选一  │
└─────────────────────────────────────────────────────────────┘
```

**解耦原则**：L0 不知道 L1/L2 是否真正调了模型；L1/L2 **不得**成为 `ingest` / 评分路径上的硬依赖。  
**互斥**：同一时刻只允许一种 mode；不得「宿主 + DeepSeek」并行各干一半且无约定。

---

## 3. 配置项（已拍板命名）

> 默认 `mode=workbuddy` = 行为与今日一致（仓库不调模型）。DeepSeek 相关键仅在 `deepseek` 模式使用。

| 环境变量 | Settings 字段（建议） | 层 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `DAILYLUMEN_LLM_MODE` | `llm_mode` | 环境差异 / 开关 | `workbuddy` | **互斥**：`workbuddy` \| `deepseek`。空配置按 `workbuddy` |
| `DEEPSEEK_API_KEY` | `deepseek_api_key` | **凭据** | `""` | 仅 deepseek 模式需要；**只进 `local/.env`**；永不入 git / 日志 / 报告 |
| `DEEPSEEK_BASE_URL` | `deepseek_base_url` | 环境差异 | `""`（或官方默认） | 仅 deepseek 模式；空则用代码内官方默认 |
| `DEEPSEEK_MODEL` | `deepseek_model` | 环境差异 | `""`（或官方默认） | 仅 deepseek 模式 |
| `DEEPSEEK_TIMEOUT_S` | `deepseek_timeout_s` | 环境差异 | `60` | 已落地 |

对齐既有规矩：

- 与 KeepStrong / ClickUp 一样：键进 `.env.example`（空值 + 中文注释），真值只在 `local/.env`。  
- **不**把 DeepSeek / 任意 LLM SDK 塞进业务层默认依赖。  
- `mode=workbuddy`：不走 HTTP 调模型；契约由宿主履行。  
- ⛔ **不要**引入统一的 `DAILYLUMEN_LLM_API_KEY` / 泛化多厂并列。

---

## 4. WorkBuddy 输入标准化契约（建议 · 契约落点正文）

> **落点**：本节为本阶段契约正文；短表见 skill **`llm-host-contract`**；  
> `daily-review-intake` skill 有指针与双 mode 步骤。

### 4.1 目标

把宿主已在做的两件事写成**可机读 / 可人工对照**的契约，使「无外部模型也能跑 L0」与「有宿主 / 有 DeepSeek 时自动化填 md」并存。

### 4.2 通道 A：素材 → 字段 / 附录（读图 / 口述）

| 项 | 约定 |
| --- | --- |
| **输入** | 用户投递的截图 / 口述 / 文档；对象日 = 当晚复盘日（intake §0） |
| **允许写** | 当日 `local/每日复盘/复盘/YYYY-MM/YYYY-MM-DD.md` 的数据块字段、打卡勾选、附录（体征 / 饮食明细 / 训练 / 学习） |
| **禁止写** | 直接写 SQLite；手改「六、四维评分」分数；把截图路径写进数据块 |
| **缺失** | 留空合法；⛔ 估算凑数；**`体脂率` 无设备可永久空**（⛔ 禁止伪造） |
| **多图冲突** | **后图非空覆盖先图**（`later_wins`）；冲突记 `conflicts` / runlog |
| **部分失败** | 合并已成功图字段；记录 `failed_images`；重试仍走客户端退避 |
| **落库** | 写完 md 后 `ingest`（评价与 summary 写完后再 `ingest` 一次）→ `finalize --apply` |
| **证据** | 收件箱可留对照素材；权威永远是复盘 md |
| **deepseek** | `llm-day --image … --date D [--review] [--write]` 或分拆 `llm-vision` / `llm-review` |

### 4.3 通道 B：事实 →「七、AI 评价与建议」

| 步骤 | 命令 / 资产 | 产出角色 |
| --- | --- | --- |
| 1 | `ai-context <日>` | **事实**（本地确定性） |
| 2 | `doctor`（看熔断 / 相对基线 / LLM 段） | **告警事实** |
| 3 | `life-decision-guide`（建议段） | **书口径排序**（宿主 skill） |
| 4 | 宿主撰写；或 `llm-review <日> [--diff] [--write]`（deepseek） | **叙事草稿**（可关 / 可空；缺节=当日无 AI 建议） |
| 5 | 人审 → 再 `ingest` + `finalize` | 入库 summary / 分数一致 |

⛔ 不得编造上下文未列出的数字。叙事不进评分。

### 4.4 与两种 mode 的关系

- **`workbuddy`（默认）**：用户可手填 md，或由 WorkBuddy **宿主 Agent**（对话/技能）按 §4.2–4.3 产出结构化结果并写入同一落点；仓库**不**发模型请求。  
- **`deepseek`**：同一 I/O 契约，由 `llm-review` / `llm-vision` **进程内调 DeepSeek API** 产出后**仍只写 md**；**不新增第二条入库路径**。  
- 无宿主、无 DeepSeek key：手填 md + 只跑 L0 CLI；系统完整可用。

### 4.5 R1 审计结论（v1.55.0）

| 模块 | 饮食/健康判定来源 | 结论 |
| --- | --- | --- |
| `ai_review` | `SCORE_THRESHOLDS` + `core.nutrition` | 权威上下文 |
| `nutrition` | `core.nutrition`（与 ai_review 同源） | ✅ 已合规 |
| `steward` | 委托 `nutrition.collect` | ✅ 已合规 |
| `coach` | 仅训练规则（`core.training`） | ✅ 无重复饮食判定 |
| 周报/月报 `analyze` | 聚合展示；无第二套缺口/分档算法 | ✅ 已合规 |

**无需为 R1 改判定代码**；禁止新增第二套算法或改四维权重。

---

## 5. 里程碑切分（完成度）

| ID | 内容 | 状态 |
| --- | --- | --- |
| **L-0** | 本文定稿 + conventions / 能力图谱指针 | ✅ |
| **L-1** | Settings + `.env.example` + doctor mode + DeepSeek urllib 骨架 | ✅ **v1.53.0** |
| **L-2** | intake 指针 + 契约 §4 | ✅ **v1.53.0** |
| **冒烟** | Vision 合成 PNG + mock；可选 `DAILYLUMEN_DEEPSEEK_LIVE=1` 真网 | ✅ |
| **L-3** | `llm-review`：ai-context → chat → 只写「七、AI」草稿 | ✅ **v1.54.0** |
| **读图 intake** | `llm-vision`：图 → 契约 → md 数据块 | ✅ **v1.54.0** |
| **可独立跑打磨** | 多图 / 重试 / `--diff` / 宿主短契约 / doctor+runlog | ✅ **v1.55.0** |
| **体脂可选 + llm-day** | 体脂可跳过；一键日流程；后图覆盖冲突；部分失败合并 | ✅ **v1.56.0** |
| **草稿/定稿 + 独立部署** | ingest 跳过未定稿；七-A/七-B；`docs/独立部署.md`；vision 硬化 | ✅ **v1.56.1** |

### 草稿 / 定稿（v1.56.1）

| 落点 | 约定 |
| --- | --- |
| **七-A · AI 草稿** | `llm-review` / 宿主写入；含「草稿 / 待人审」 |
| **七-B · 定稿** | 人审通过后保留；去掉草稿标记 |
| **文件头 pending** | `<!-- dailylumen:llm-pending-review -->`（vision/review `--write` 戳） |
| **`local/每日复盘/草稿箱/`** | 侧车未定稿；与收件箱同级，**永不** ingest |
| **`ingest`** | 默认跳过未定稿；`--allow-ai-draft` 强制 |

**真实截图**：请投放到本机 `local/每日复盘/收件箱/`（jpg/png）；⛔ 勿 commit 进 git。  
无真实图时用仓库合成 fixture 证明流程。独立部署步骤见 [`独立部署.md`](独立部署.md)。

### 下一步（可选，未开工）

- 评价草稿与 `life-decision-guide` 书条目的自动挂靠（仍须人审）。  
- 附录明细表（食物明细）的结构化扩展。  
- ⛔ 仍不引入 SDK；不改四维；不建「只进库」路径；⛔ 不伪造体脂。

---

## 6. 非目标（红线）

- ⛔ 不改四维评分权重 / 锚点 / 熔断参数，不重算历史分。  
- ⛔ 不把 `local/` 日记真值、截图、`.env` 密钥纳入 git。  
- ⛔ 不新建「只进库不落 md」的 LLM 写库路径（**先 md 再 ingest**）。  
- ⛔ 不把 LLM / DeepSeek SDK 做成默认依赖；不打开 `FEATURES["new_day"]`；不重建定时任务。  
- ⛔ 不合并 `habit_logs` / `personal_tracks`；训练日主判据仍以练练 `completed` 为准。  
- ⛔ 不强行统一 `DAILYLUMEN_LLM_API_KEY`；不并行多厂 provider 枚举。

---

## 7. 决策点归档（已拍板）

| ID | 原问题 | 拍板 |
| --- | --- | --- |
| **D1** | 本地 / 仓库内 LLM 调用要不要进仓库？ | **要**：默认 `workbuddy`；可选 `deepseek`。L-3/读图已落地。 |
| **D2** | 默认 provider 语义？ | 与 **mode 同一维度**；默认 **`workbuddy`**。 |
| **D3** | API key 变量名？ | **按提供方分**：`DEEPSEEK_*`；**不要**统一 `DAILYLUMEN_LLM_API_KEY`。 |
| **D4** | Vision 是否进首期？ | 首期否；**v1.54.0 已后置落地** deepseek Vision intake。 |
| **D5** | 契约落点？ | 正文在本草案 §4 + intake / **`llm-host-contract`** 短表。 |

---

## 8. 指针

- `.workbuddy/skills/dailylumen-conventions/SKILL.md`（范围边界旁）  
- `.workbuddy/skills/llm-host-contract/SKILL.md`（宿主短表）  
- `docs/能力图谱.md`（「AI 评价与建议」）  
- `.workbuddy/skills/daily-review-intake/SKILL.md`（契约指针 + **双 mode 操作步骤**）  
- `.env.example`（`DAILYLUMEN_LLM_MODE` + `DEEPSEEK_*`）

---

*完。L-1～打磨已在 v1.55.0 收口；体脂可选 + llm-day 在 v1.56.0；草稿/定稿与独立部署在 v1.56.1。*

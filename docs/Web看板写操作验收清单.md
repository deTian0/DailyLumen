# Web 看板写操作真机验收清单（B8）

> **给谁用**：用户本人按清单逐项手动点。  
> **谁不做**：agent / Cursor **不**对真实 ClickUp / 练练执行确认；本仓库自动化测试一律 mock。  
> **核实**：2026-11-12，对照 `review_tool/api/writes/*.py` 注册表共 **18** 条动作（`registered_actions()`），含 D1 `keepstrong_sync`；代码基线 **v1.93.0**。

## 总前置（每项开始前）

1. 启动：`python -m review_tool serve --enable-write`（未开写开关则 plan 可预览、confirm 被拒）。
2. 已配置 `local/.env` 凭据（ClickUp / 练练 / DeepSeek 按动作需要）；看板 `DAILYLUMEN_WEB_KEY`。
3. **写库类动作前**：确认 `.workbuddy/backup/`（或 serve 配置的 backup 目录）可写；系统会在 confirm 前自动备份 `reviews.db`。
4. 流程一律：**页面入口 → 预览（plan）→ 核对预览文案 / CLI 等价命令 → 确认（confirm）**；token 约 5 分钟有效、一次性。
5. 回滚总原则：
   - **ClickUp / 练练远端**：在对应 App 手动改回（写回不可从本库撤销）。
   - **库**：用 confirm 返回的 backup 文件名，从备份目录还原 `local/reviews.db`（先停 serve）。
   - **md**：`git checkout -- <文件>` 或对照备份；含待人审标记的草稿勿强行 ingest。

## 副作用总表（核实后）

| # | 动作 id | Web 入口 | 写远端 | 写库 | 写 md / 文件 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `task_create` | 今日 · 新建任务 | ✅ ClickUp | — | — | |
| 2 | `task_status` | 今日 · 单条完成/改状态 | ✅ ClickUp | — | — | |
| 3 | `task_batch` | 今日 · 批量完成 | ✅ ClickUp | — | — | ≤20 条 |
| 4 | `clickup_pull` | 今日 · 拉取完成快照 | 读 ClickUp | ✅ `clickup_done` | — | 按天整替；写前备份 |
| 5 | `clickup_habit` | 生活 · 习惯/训练 · 代勾练练健身 | ✅ ClickUp | ❌ **不写** `habit_logs` | — | B15；≠ 训练入库 |
| 6 | `habits_sync` | 生活 · 习惯 sync | 读 ClickUp | ✅ `habit_logs` | — | **不碰** `personal_tracks`（R3） |
| 7 | `ai_draft` | 报告 · AI 草稿 | — | — | ✅ 复盘 md | 带待人审；ingest 默认跳过 |
| 8 | `finalize` | 报告 · 定稿 | — | — | ✅ 复盘 md | **不**自动 ingest |
| 9 | `ingest` | 报告 / 读图串联 | — | ✅ `daily_reviews` 等 | — | 写前备份 + 回读 |
| 10 | `vision` | 报告 · 读图日流程 | （调 LLM） | — | ✅ 复盘 md 数据块 | 待人审；先 md 后库 |
| 11 | `inbox_archive` | 报告 · 读图日流程 · 归档 | — | — | ✅ 移动收件箱文件 | → `收件箱/已处理/日/` |
| 12–17 | `ks_*` ×6 | 生活 · 练练写回 | ✅ 练练 | ❌ **不落库** | — | 不可撤销 |
| 18 | `keepstrong_sync` | 生活 · 训练 · 练练→复盘 md | 读练练 | ❌ **不写库** | ✅ 复盘 md | D1；≠ `ks_*`；入库另走 ingest |

练练 6 动作：`ks_set_weight` / `ks_log_body` / `ks_schedule` / `ks_create_template` / `ks_replace_template_actions` / `ks_plan_command`。

---

## 分项清单

### 1–3. ClickUp 任务：新建 / 改状态 / 批量完成

| 字段 | 内容 |
| --- | --- |
| 动作 | `task_create` · `task_status` · `task_batch` |
| 入口 | **今日**页：待办单条「完成」、批量栏、新建任务 |
| 前置 | `--enable-write`；ClickUp token / list 可用 |
| 步骤 | 选任务或填标题 → 预览 → 确认 |
| 预期 | ClickUp 任务状态/新建成功；**库与 md 无变化**；预览 CLI ≈ `clickup-task … --apply` |
| 回滚 | ClickUp 里手动改回状态 / 归档或删除误建任务 |
| 验证 | 打开 ClickUp 对应 list；本机 `reviews.db` mtime / 行数应不变 |

### 4. clickup-pull 完成快照

| 字段 | 内容 |
| --- | --- |
| 动作 | `clickup_pull` |
| 入口 | **今日** →「拉取完成快照」 |
| 前置 | 写开关；ClickUp；备份目录可写 |
| 步骤 | 预览近 N 天条数 → 确认（整天替换 `clickup_done`） |
| 预期 | 返回 `backup` 文件名；`clickup_done` 按天条数与预览一致；不写复盘 md |
| 回滚 | 用 backup 还原整库 |
| 验证 | `python -c` 读库或 Web 今日完成数变化；对照备份 |

### 5. clickup-habit（代勾「练练健身」）

| 字段 | 内容 |
| --- | --- |
| 动作 | `clickup_habit` |
| 入口 | **生活** · 习惯 / 训练 · `ClickupHabitWrite` |
| 前置 | 写开关；ClickUp「习惯与打卡」有当日任务 |
| 步骤 | 预览（含练练旁证提示）→ 确认 |
| 预期 | 只 PUT ClickUp；响应 `db_changed=False`；**不写** `habit_logs` / `training_*` / 四维分 |
| 回滚 | ClickUp 手动取消勾选 |
| 验证 | ClickUp 习惯已勾；`SELECT count(*) FROM habit_logs WHERE date=?` 行数不变（ Continuity 入库仍靠 `habits_sync`） |

### 6. habits_sync

| 字段 | 内容 |
| --- | --- |
| 动作 | `habits_sync` |
| 入口 | **生活** · 习惯卡 ·「同步习惯」 |
| 前置 | 写开关；ClickUp；备份目录 |
| 步骤 | 预览将写入的 habit 行（明示不动 `personal_tracks`）→ 确认 |
| 预期 | 只写 `habit_logs`；写前备份；回读键集合一致 |
| 回滚 | 备份还原库 |
| 验证 | 预览列出的 key 出现在 `habit_logs`；`personal_tracks` 无新增同名交叉（R3） |

### 7. AI 草稿写入

| 字段 | 内容 |
| --- | --- |
| 动作 | `ai_draft` |
| 入口 | **报告** ·「写入与定稿」· AI 草稿 |
| 前置 | 写开关；DeepSeek（或当前 LLM mode）；目标日 md 存在 |
| 步骤 | 预览差异 → 确认写入「七-A」草稿段 |
| 预期 | 只改 md；带待人审标记；**不写库** |
| 回滚 | `git checkout` 该日 md |
| 验证 | md 含草稿标记；`ingest` 默认跳过该日 |

### 8. 定稿

| 字段 | 内容 |
| --- | --- |
| 动作 | `finalize` |
| 入口 | **报告** · 定稿 |
| 前置 | 已有待人审草稿 |
| 步骤 | 预览并排 diff → 确认 |
| 预期 | 只改 md（去 pending）；**不**自动入库；可串到 ingest 预览 |
| 回滚 | git 还原 md |
| 验证 | pending 标记消失；库尚未更新直至单独 confirm ingest |

### 9. ingest 单文件

| 字段 | 内容 |
| --- | --- |
| 动作 | `ingest` |
| 入口 | **报告** · 入库；读图流程也可串联 |
| 前置 | 写开关；md 已定稿（或勾选 allow-ai-draft，一般不建议）；备份目录 |
| 步骤 | 预览将入库字段 → 确认 |
| 预期 | 写库前备份；`daily_reviews`（及侧车）更新；回读四维分 |
| 回滚 | 备份还原库（md 保持为权威源时可再 ingest） |
| 验证 | Web 今日/分析数据更新；`doctor` 对账无该日「未入库」 |

### 10. vision（读图写数据块）

| 字段 | 内容 |
| --- | --- |
| 动作 | `vision` |
| 入口 | **报告** · 读图日流程（`VisionDay`） |
| 前置 | 写开关；LLM；选图（上传或收件箱） |
| 步骤 | ① 字段预览（可不写）→ ② 确认写 md 数据块 |
| 预期 | 只写 md（待人审）；**不写库**；下一步应定稿再 ingest |
| 回滚 | git 还原 md |
| 验证 | md 数据块字段变化 + pending 标记 |

### 11. inbox_archive

| 字段 | 内容 |
| --- | --- |
| 动作 | `inbox_archive` |
| 入口 | 读图日流程 · 归档本次收件箱图 |
| 前置 | 写开关；文件仍在 `收件箱/` |
| 步骤 | 预览源→目标 → 确认移动 |
| 预期 | 文件到 `收件箱/已处理/<日>/`；不写库 |
| 回滚 | 手动移回 `收件箱/` |
| 验证 | 源路径不存在、目标存在；`doctor` 收件箱待处理数下降 |

### 12–17. 练练写回（6 动作）

| 字段 | 内容 |
| --- | --- |
| 动作 | `ks_set_weight` / `ks_log_body` / `ks_schedule` / `ks_create_template` / `ks_replace_template_actions` / `ks_plan_command` |
| 入口 | **生活** · 练练写回卡（`KeepStrongWrite`） |
| 前置 | 写开关；练练 API Key；文案明示「写回不落库、不可撤销」 |
| 步骤 | 填表 → 预览 → 确认（POST 练练，`user_confirmed`） |
| 预期 | 练练 App 侧变化；响应 `db_changed=False`；**本库 / md 无写入** |
| 回滚 | 仅能在练练 App 手动改回（系统无撤销） |
| 验证 | 练练界面目视；`reviews.db` mtime 不变 |

---

## Agent / CI 边界（再声明）

- 单元 / API / Vitest：**只 mock** upstream；禁止对真 ClickUp / 练练点「确认」。
- 本清单勾选由**用户**在真机完成；完成后可在本文件末尾自行追加「验收日期 / 勾选人」。

## 核实记录

| 项 | 值 |
| --- | --- |
| 日期 | 2026-11-09 |
| 注册表条数 | 17（与 `registered_actions()` 一致） |
| 代码基准 | `ea4e2ca0772921a79ac240184568cd3c746c9e4c` |
| 特例 | `clickup_habit` 不写 `habit_logs`；`ks_*` 六动作不落库 |

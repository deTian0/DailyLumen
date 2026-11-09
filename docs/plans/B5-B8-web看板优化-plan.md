# Plan：Web 看板 B5–B8 四项优化（交付 Cursor 执行）

> 生成：2026-11-09（基于 v1.83.1 实测代码结构）
> 执行者：Cursor。口径权威：`.cursor/rules/dailylumen.mdc` → `.workbuddy/skills/dailylumen-conventions/SKILL.md`。
> 四项相互独立，建议按 B7 → B5 → B6 → B8 顺序做（前两个最小、可先熟悉前端测试链路）。

## 全局约束（每项都适用，违反 = 返工）

1. **架构分层铁律**：`api/` 是独立第五层（可依赖其余层，其余层禁止依赖 api）；fastapi/uvicorn 只准出现在 `api/`。B6 若需后端改动，结构化口径只许抽到 `review_tool/reports/doctor.py`，**不许在 api 层另算口径**（R1 单源）。
2. **只读查询**走 `get_readonly_conn()`；本 plan 四项**全部不新增写端点**。
3. **CLI 输出与 md 文本不变**（B7 明确只在前端解析）。
4. **测试链路**：
   - Python：`./.venv/Scripts/python.exe -m unittest discover -s tests -t .`（当前基线 1268 OK / skip 2，不许掉）
   - 前端：`cd web && npm ci && npm test`（Vitest ~54 例）
   - lint：`ruff check .`（ruff 在 `D:/soft/path/miniconda3/Scripts/ruff.exe`）
5. **提交纪律**：每项一个 feat commit（语义化提交），B5/B7 各 bump 一个 patch 版本（pyproject.toml + `review_tool/__init__.py` + `docs/设计说明.md` 变更日志三处同步）；B6/B8 视改动量合并 bump。**不推 tag**（B10 已定调不补打）。
6. **本机注意**：写文件后回读校验；改 `web/src` 才需要 npm build（`web/dist` 已入库，build 后须一并提交）。

---

## B5 · 图表系列开关偏好记忆（P2，前端小项）

**目标**：图例开关状态按 kind 持久到 localStorage，刷新后保持；系列定义变化时旧偏好自动失效。

**现状（实测）**：
- `web/src/lib/chartOption.js:42` 已有 `defaultLegendSelected(series, kind)`（默认前 2 条选中）
- `web/src/components/EChart.jsx` 尚未监听 `legendselectchanged` 事件

**实现要点**：
1. 新增 `web/src/lib/legendPrefs.js`：
   - `loadLegendSelected(kind, series)`：localStorage 读 `dailylumen.legend.<kind>.v1`；校验 JSON + 键集合与当前 series 匹配，不匹配/损坏/缺失 → 返回 null（回退 `defaultLegendSelected`）
   - `saveLegendSelected(kind, selected)`：写前 JSON.stringify，异常静默
2. `chartOption.js::defaultLegendSelected` 增加可选参数或有偏好时由调用方覆盖
3. `EChart.jsx` 监听 `legendselectchanged`，防抖 300ms 后保存
4. key 带版本号 `v1`（系列改名后旧偏好自动失效的机制靠键集合校验 + 版本号）

**验收（写 Vitest）**：
- [ ] 有合法偏好 → 覆盖默认
- [ ] 无偏好 / JSON 损坏 / 系列键集合变了 → 回退 `defaultLegendSelected`
- [ ] 保存失败（localStorage 不可用）不抛错

---

## B6 · 体检页结构化视图（P2，前后端中项）

**目标**：体检页按「分项状态 ✅/⚠️ + 计数 + 建议」卡片渲染，替代 prose 全文直出；保留「查看原文」折叠。

**现状（实测，比路线图预估的省事）**：
- `review_tool/reports/doctor.py::diagnose()` **已返回结构化 dict**（各分项已在内）
- `review_tool/api/queries.py::doctor()` 已把 `result` 一并放进返回（`{healthy, text, result}`）
- `review_tool/api/routes_reports.py::DoctorOut`（line 48）可能只声明了部分字段 —— 需核对
- 前端页面：`web/src/pages/Doctor.jsx`

**实现要点**：
1. 核对 `DoctorOut` 是否透出 `result`；若未透出，**补模型字段**（透传，不改口径）——若需要裁剪字段，裁剪逻辑放 reports 层新函数（如 `summarize(result)`），api 只调用
2. CLI `doctor` 若要改为基于 `diagnose()` 结果格式化，**行为必须逐字不变**（用现有 doctor 测试对拍）
3. `Doctor.jsx` 重构：顶部健康结论（绿/黄横条）→ 分项卡片网格（每张卡：分项名 / 状态 icon / 关键计数 / 建议）→ 底部 `<details>`「查看原文」渲染原 `text`
4. 深浅主题文字色遵守当前 IDE 主题变量

**验收**：
- [ ] Python 对拍测试：`summarize(diagnose(...))` 输出与 CLI `doctor` 逐项结论一致（新增测试文件放 `tests/reports/`）
- [ ] Vitest：Doctor.jsx 渲染分项卡片、状态 icon、原文折叠存在
- [ ] 手工验证：`uv run python -m review_tool serve` 后体检页无 prose 直出（原文只在折叠区）

---

## B7 · 周报 ASCII 条 → CSS 进度条（P2，前端小项）

**目标**：周报 md 里的 `████░░` 进度条在 Web 端渲染成真 CSS 进度条；CLI 与 md 文件保持原样。

**现状（实测）**：
- 转换入口：`web/src/lib/prose.js::toProseSource()`（CLI 风格全文 → Markdown 的前端呈现层，本来就约定「不改后端文案」）
- 渲染组件：`web/src/lib/markdown.jsx`

**实现要点**：
1. `prose.js` 新增 ASCII 条识别：正则匹配 `█+░+`（含全量/部分填充变体，注意 ▓ 等中间字符），从相邻文本提取标签与分母（周报里形如 `标签 ██████░░░░ 5/7`）
2. 转成 markdown 中可识别的占位（或直接返回 React 节点，取决于 markdown.jsx 的管线），最终 DOM 元素带 `role="progressbar"`、`aria-valuemin/max/now`
3. 样式：`web/src/styles/` 加进度条样式，颜色跟随主题变量（涨红跌绿不适用此处，用中性主色即可）

**验收（写 Vitest，放 `prose.test.js`）**：
- [ ] 标准 `████░░` 被识别并产出 progressbar 元素
- [ ] 含分数 `5/7` 的行 aria-valuenow=5 / max=7
- [ ] 不认识的格式（如只有 `█` 无上下文、纯文本混排）按原样显示
- [ ] CLI 侧零改动：`tests/` 无需新增，跑全量确认无回归即可

---

## B8 · 写操作真机验收清单（P2，纯文档项）

**目标**：整理一份「用户本人按清单逐项手动点」的验收文档；agent/Cursor 不执行真实确认。

**位置**：新建 `docs/Web看板写操作验收清单.md`（并在 `docs/Web看板路线图.md` B8 节加链接、标记完成）。

**必须核实的点（路线图原话：「上表写库/写 md 列以实现为准，整理时逐项对照核实后再定稿」）**：
- 逐个读 `review_tool/api/writes/*.py` + `review_tool/api/write_ops.py`，核实 17 条 plan 端点的真实副作用（写远端 / 写库 / 写 md / 移动收件箱文件）
- 注意两个特例口径：练练写回 6 动作**不落库不可撤销**；`clickup-habit` **不写 `habit_logs`**

**每项清单字段**（沿用路线图 B8 已给的两张表 + 补全）：
1. 动作名 + 对应 Web 入口页面
2. 前置条件（`--enable-write` 启动、已备份库、所需凭据）
3. 操作步骤（页面路径 → 按钮 → plan → confirm token）
4. 预期结果（库里哪张表 / 哪个 md / 远端哪里的变化，含验证命令）
5. 回滚方式（ClickUp 手动改回 / 用 `.workbuddy/backup/` 快照恢复库 / git 还原 md）

**验收**：
- [ ] 覆盖全部 17 条写动作，无遗漏
- [ ] 每条副作用声明与 `writes/*.py` 代码一致（Cursor 需在文档末尾附核实日期与 commit SHA）
- [ ] 纯文档改动，无代码变更；提交为 `docs:` commit

---

## 交付顺序与提交计划

| 顺序 | 项 | 类型 | commit | 版本 |
|---|---|---|---|---|
| 1 | B7 进度条 | feat(web) | `feat(web): 周报 ASCII 进度条前端渲染` | patch+1 |
| 2 | B5 图例偏好 | feat(web) | `feat(web): 图例开关偏好持久化` | patch+1 |
| 3 | B6 体检结构化 | feat(web+api) | `feat(web): 体检页结构化视图` | patch+1 |
| 4 | B8 验收清单 | docs | `docs: 写操作真机验收清单` | 不 bump（纯文档） |

完成后：`main` 推 GitHub（PowerShell + GIT_SSH 方式），远端 ls-remote 核对。全部绿灯（1268+ / Vitest 全过 / ruff clean）才算完。

## 明确不做（防止 Cursor 自作主张）

- ❌ 不打 tag、不补历史 tag（B10 已定调）
- ❌ 不改 `local/.env`、不动体重目标带
- ❌ 不新增任何写端点 / 不动 plan→confirm 机制
- ❌ 不改 CLI 输出格式与周报 md 生成文本
- ❌ 不动 `--host` 绑定、不放开只读默认

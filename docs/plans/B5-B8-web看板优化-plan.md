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

## B6 · 体检页结构化视图（P2，前后端中项）✅ v1.86.0

**目标**：体检页按「分项状态 ✅/⚠️ + 计数 + 建议」卡片渲染，替代 prose 全文直出；保留「查看原文」折叠。

**实现要点（已落地）**：
1. `reports/doctor.py::summarize`：六闸对齐 `is_healthy`；结论对齐 `render`
2. `DoctorOut.summary` 透传；CLI `render` **未改**
3. `Doctor.jsx`：横条 → 卡片网格 → `<details>查看原文`
4. 对拍：`tests/reports/test_doctor_summarize.py`；Vitest `Doctor.test.jsx`

**验收**：
- [x] summarize ↔ is_healthy / render 结论
- [x] 前端分项卡片 + 原文折叠
- [ ] 手工 serve 目视（可选，agent 不强制）

---

## B7 · 周报 ASCII 条 → CSS 进度条（P2，前端小项）✅ v1.85.0

**目标**：周报 md 里的 `████░░` 进度条在 Web 端渲染成真 CSS 进度条；CLI 与 md 文件保持原样。

> ⚠️ **勘误（执行前已纠正）**：不要只改 `prose.js`。周报走 `Reports` → `Markdown`（`web/src/lib/markdown.jsx`）表细胞；
> 真实格式是 `reports/analyze.py::_md_bar` 的 `█`/`░`（宽约 10）；可选兼容 CLI `_bar` 的 `█`+`·`。
> `prose.js` 只负责 CLI 风格全文 → md，不是周报主路径。

**现状（实测）**：
- 周报渲染：`web/src/lib/markdown.jsx` 表细胞
- 条形生成：`review_tool/reports/analyze.py::_md_bar`（`█`/`░`）

**实现要点（已落地）**：
1. `asciiBar.js`：`parseWholeBar` / `splitAsciiBars`；分数行覆盖 aria now/max
2. `markdown.jsx` 表细胞 + 行内 → `role="progressbar"`
3. `content.css`：`.md-bar*`，颜色 `--accent`

**验收**：
- [x] 标准 `█░` 产出 progressbar
- [x] 含分数 `5/7` → aria-valuenow=5 / max=7
- [x] 不认识的格式原样显示
- [x] CLI / md 零改动

---

## B8 · 写操作真机验收清单（P2，纯文档项）✅

**目标**：整理一份「用户本人按清单逐项手动点」的验收文档；agent/Cursor 不执行真实确认。

**位置**：[`docs/Web看板写操作验收清单.md`](../Web看板写操作验收清单.md)（路线图 B8 已链并标记完成）。

**验收**：
- [x] 覆盖全部 17 条写动作
- [x] 副作用与 `writes/*.py` 一致（核实基准 `ea4e2ca`）
- [x] 纯文档；`docs:` commit；不 bump 版本

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

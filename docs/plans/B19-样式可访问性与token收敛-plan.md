# Plan：B19 · 主题可访问性与样式 token 收敛

> 生成：2026-11-12（基于 v1.91.0 实测样式）
> 执行者：agent。口径权威：`.workbuddy/skills/dailylumen-conventions/SKILL.md`。
> 目标版本：**v1.92.0**；一个 feat commit；**不打 tag、不 push**。
> 性质：**只动呈现层**。不改业务逻辑、API 契约、后端 SVG/JSON 输出；不引入新依赖。

---

## 0. 一句话目标

在不改品牌 hue、不动业务的前提下，让三套主题的正文文字 ≥ **4.5:1**、图形与 UI 边界 ≥ **3:1**，所有 `var(--x)` 都有定义，图表系列色跟随主题，并加一层可自动回归的对比度测试。

---

## 1. 动机（实测）

| # | 问题 | 证据 |
| --- | --- | --- |
| 1 | 暗色主色上的文字几乎不可读 | `--on-accent` 固定白字；暗色 accent `#2dd4bf` 上仅 **1.86:1**；light `#109485` **3.75**；omni `#007aff` **4.02** |
| 2 | 暗色「已完成」步骤圆点白字不可读 | `writes.css` 用 `--ink-green` 当实心底 + 白字；dark 的 `--ink-green` 是浅薄荷，约 **1.4:1** |
| 3 | 搜索框键盘焦点不可见 | `layout.css` `.search input { outline: 0 }` 特异性压过全局 `:focus-visible` |
| 4 | JSON 编辑器文字色是无效变量 | `content.css` `color: var(--ink)`，全项目无 `--ink` |
| 5 | 图表系列色不跟主题 | 后端写死 7 色；dark 学习 **2.94**、系统 **3.06**；light 工作 **2.94**，低于图形 3:1 |

附带问题：`tokens.css` 有 45 条零引用声明；`content/tasks/feedback` 有 13 处硬编码 rgba；圆角 token 只覆盖 14 处，仍有 25 处散落硬编码。

---

## 2. 范围

**做：**

- `web/src/styles/tokens.css` 及 `layout / cards / tasks / content / feedback / writes / login.css`
- `web/src/lib/chartOption.js` + 新增 `chartTheme.js`
- 表单控件文字/占位符/选中/自动填充的跨主题可读性
- 前端测试、`web/dist`、版本四处、路线图、设计说明

**不做（留给后续）：**

- B20：prose 行宽、移动端导航/触控目标、打印样式、字号体系、首屏内联主题脚本、ECharts reduced-motion
- B21：`jest-axe` / Playwright 视觉回归
- B22：「跟随系统」第四种模式 / 主题切换过渡
- 后端 `reports/chart.py`、`api/queries.py` 的 SVG/JSON 输出
- 布局重排、组件重写、引入 Tailwind/MUI/图标库、默认暗色、换品牌青绿、打 tag

---

## 3. 目标 token 表

保留 `--accent` 作为**装饰填充/图标/进度条**的品牌色；新增 `--accent-strong`（实心按钮/选中态）与 `--accent-ink`（链接/状态文字）。

| token | light | dark | omni | 用途 |
| --- | --- | --- | --- | --- |
| `--accent` | `#109485`（不变） | `#2dd4bf`（不变） | `#007aff`（不变） | 装饰填充、图标底、进度条 |
| `--accent-strong` 🆕 | `#0d7c6f` | `#2dd4bf` | `#0066d6` | 主按钮、tab/seg/主题选中、选中日 |
| `--accent-ink` 🆕 | `#0a6b60` | `#2dd4bf` | `#005ec4` | 链接、状态文字、pill 文字 |
| `--on-accent` | `#ffffff` | `#062a26` | `#ffffff` | strong 底上的文字 |
| `--on-status` 🆕 | `#ffffff` | `#062a26` | `#ffffff` | ink 实心状态底上的文字 |
| `--muted` | `#5a6a78`（不变） | `#9aa8b6`（不变） | `#6e6e73` | 次级文字 |
| `--ink-amber` | `#8a5a00` | `#fcd34d`（不变） | `#8a5a00` | 警告文字/状态 |
| `--ink-blue` | `#0a6b60` | `#5eead4`（不变） | `#005ec4` | 蓝色 pill 文字 |
| `--border-input` 🆕 | `#8b939c` | `#6b7684` | `#8b939c` | 输入框边界（≥3:1） |

关键对比度：light strong 白字 **5.09**、omni **5.42**、dark 深字 **8.25**；light ink 在页面底 **5.56**、omni **5.54**、dark **8.50**；omni muted 在页面底 **4.54**；light/omni 的 ink-amber 在 10% 浅底上 **5.13+**。

语义 token（只定义一次，随主题变量解析）：

```css
--ok-soft / --ok-border
--warn-soft / --warn-border
--crit-soft / --crit-border
--info-soft / --info-border
--hover-tint
--code-bg
--field-bg
```

---

## 4. 任务分解

### 4.1 颜色与可访问性（P0）

- [ ] `--on-accent` 按主题覆盖；新增 `--on-status`
- [ ] 新增 `--accent-strong` / `--accent-ink`，替换 6 处 `color: var(--accent)` 文字用法和 6 处实心选中态
- [ ] `.rstep-done .rstep-dot` 改用 `--on-status`
- [ ] omni `--muted` → `#6e6e73`；light/omni `--ink-amber` → `#8a5a00`
- [ ] `.pill-blue` 文字改用 `--ink-blue`；`.pill-amber` 边框/底色改用语义 token
- [ ] 新增语义 token，替换 13 处硬编码 rgba
- [ ] `--border-input` 替代输入框的 `--border`，达到 3:1

### 4.2 焦点与无效引用

- [ ] `.search:has(input:focus-visible)` 焦点环；保留 input `outline: 0`
- [ ] `content.css` `var(--ink)` → `var(--text)`
- [ ] 合并 `tokens.css` 与 `content.css` 两份 `.visually-hidden`
- [ ] 去掉各处 2px 焦点覆盖，统一走全局 3px + `--focus`

### 4.3 图表主题色

- [ ] 新增 `web/src/lib/chartTheme.js`：按 series `key` 映射 light/dark 可访问色，未知 key 回退后端 `color`
- [ ] `chartOption.js::lineSeries` 改用 `seriesColor(s, theme)`
- [ ] 训练柱状图 / 营养双轴同样使用映射
- [ ] 后端 JSON / SVG 输出保持不变（R1 只约束数据，不约束展示色）

### 4.4 Token 收敛

- [ ] 删除 45 条零引用声明：`--chart-*`（7×3）、`--blue/green/red/amber`（4×3）、`--shadow-out/-in` 系列（4×3）
- [ ] 保留并正式使用 `--ink-blue`
- [ ] 增加圆角档位：`--radius-2xs: 6px`、`--radius-xs: 10px`；替换散落硬编码
- [ ] `--chart-*` 删除后，图表 chrome 只有 `chartOption.js::chartChrome` 一个来源

### 4.5 表单文字与填充内容

> 本项专门覆盖用户提醒的「文字框填充内容的变化」：换主题后，已输入内容不能看不见。

- [ ] 全局 `input, textarea, select { color: var(--text); caret-color: var(--accent-ink); }`
- [ ] `::placeholder { color: var(--muted); opacity: 1; }`
- [ ] `::selection { background: var(--accent-soft); color: var(--text); }`
- [ ] `:-webkit-autofill` / `:autofill`：文字用 `--text`，背景用 `--surface`，避免 Chrome 黄底
- [ ] 搜索框、新建任务、练练内联表单、JSON 编辑器、登录 key 框逐个主题检查：已输入文字、占位符、选中、光标、自动填充

### 4.6 测试与验收

- [ ] 新增 `web/src/styles/tokens.test.js`：
  - 解析 `tokens.css` 三套主题块
  - 断言 `text/surface`、`text/bg`、`muted/surface`、`muted/bg`、`text/surface-2`、`muted/surface-2`、`accent-ink/surface|bg`、`on-accent/accent-strong`、`on-status/ink-green`、`ink-*/surface` 全部 ≥4.5
  - 断言 `border-input/surface` ≥3.0
  - 断言 `accent-ink/accent-soft`（可合成的主题）≥4.5
- [ ] 新增「未定义 CSS 变量」测试：扫描所有 `var(--x)`，断言 `tokens.css` 有定义
- [ ] 新增 `chartTheme.test.js`：每个映射色对主题表面 ≥3.0；未知 key 回退
- [ ] `cd web && npm test` 全绿（基线 84 例）
- [ ] `npm run build` 通过，`web/dist` 一并提交
- [ ] Python：`1271 tests OK / 2 skipped` 不变；`ruff check .` 全绿
- [ ] 手工键盘走查：Tab 到搜索框有焦点环；主题切换按钮有可见焦点
- [ ] 三主题 × 今日/报告/分析/登录截图，放 `local/screenshots/v192-a11y/`（gitignore 区）

### 4.7 文档与版本

- [ ] 版本四处对齐：`pyproject.toml`、`review_tool/__init__.py`、`README.md`、`docs/设计说明.md`
- [ ] 顺手提交遗留的 `uv.lock` 版本同步（1.91.0 → 1.92.0）
- [ ] `docs/Web看板路线图.md` 增加 B19 小节 + B 项总览
- [ ] `设计说明.md` 记录 before/after 对比度表与 token 迁移
- [ ] 一个 commit：`feat(web): B19 主题可访问性与样式 token 收敛（v1.92.0）`
- [ ] 不打 tag、不推远端（按 B10）

---

## 5. 验收标准（硬指标）

| 项 | 标准 |
| --- | --- |
| 正文对比度 | 三主题所有正文/链接/按钮文字 ≥ 4.5:1 |
| 图形对比度 | 图表系列、状态点、进度条 ≥ 3:1 |
| 输入框 | 已输入文字、占位符、选中、自动填充在三主题均清晰可见 |
| 焦点 | 所有可交互元素键盘可见焦点，搜索框不例外 |
| 变量完整性 | `var(--x)` 引用 100% 有定义 |
| 硬编码色 | `styles/*.css` 中除 `tokens.css` 外无业务 hex/rgba（图表色集中在 `chartTheme.js`） |
| 回归 | Vitest 84+ 全绿；build 通过；Python 1271/2 skip；ruff 全绿 |
| 视觉 | 三主题截图人工过一眼；品牌 hue 不变，仅深浅与文字色调整 |

---

## 6. 风险与回滚

- **主色变深**：`--accent` 保持原值，只把实心控件切到 `--accent-strong`，视觉变化可控；不满意可单独回退 token 块。
- **`color-mix` 兼容**：语义 soft/border 使用 `color-mix()`；目标浏览器为现代 Chromium/Firefox/Safari。
- **对比度测试脆弱**：解析只覆盖 `tokens.css` 的简单 hex / rgba 声明，不解析复杂表达式；主题块结构变更时测试会明确报错。
- **图表映射漏 key**：未知 key 回退原色 + 测试覆盖 fallback；未来新增 series 只需补一行。
- **本机写盘**：按项目约定，改完回读校验；`git status` 验真，不拿 `grep -c '\r'` 当红线。

---

## 7. 工作量

约 **0.5–1 个工作日**，涉及 ~10 个前端文件 + 3 个测试文件 + 4 处版本文档。无新增依赖。

---

## 8. 后续（不在本里程碑）

- **B20**：阅读与移动端（prose 72–78ch、移动导航/触控目标、打印样式、首屏内联主题脚本、ECharts reduced-motion）
- **B21**（可选）：`jest-axe` + Playwright 三主题截图回归
- **B22**（可选）：增加「跟随系统」第四种模式与主题切换过渡

---
name: life-steward-daily
description: DailyLumen 总管家三段 SOP —— 晨间 brief、夜间复盘编排、周度六段合一报告。适用于「早上好 / 今天怎么安排」「把今天复盘弄一下」「出周报」这类请求。触发词：早上好、今天怎么安排、晨间 brief、夜间复盘、出周报、总管家、steward。
agent_created: true
---

# 总管家日常编排（晨间 / 夜间 / 周度）

> v1.18.0 / M14。编排层是**入口**，不是新算法：数字一律来自既有 CLI / 模块，
> 本 skill 只规定**何时跑什么、按什么顺序说**。
> 项目口径见 `dailylumen-conventions`；夜间素材→成品见 `daily-review-intake`。
>
> ⛔ **不新增定时任务**。一切按用户开口触发。

## 统一命令

```bash
PY="C:/Users/63516/.workbuddy/binaries/python/versions/3.13.12/python.exe"
$PY -m review_tool steward --slot morning [YYYY-MM-DD] [--todo "…"]…
$PY -m review_tool steward --slot evening [YYYY-MM-DD]
$PY -m review_tool steward --slot week [ISO周|YYYY-MM-DD]
# 结构化：加 --json
```

每个数字块都带 `source=…`，可对照同名 CLI 复核。

---

## 段 A · 晨间 brief

**触发**：用户说「早上好 / 今天怎么安排 / 晨间 brief」。

**步骤**

1. 跑 `steward --slot morning`（默认锚点 = 库内最近一天；可显式给今天日期）。
2. 待办 Top 3：先 `clickup --stdout` 取「进行中」，再用  
   `steward --slot morning --todo "…" --todo "…" --todo "…"` 注入；  
   或在回复里直接摘 clickup 前 3 条（**不要编造任务**）。
3. 按输出四段口头复述给用户：
   - 昨日四维 + 熔断（`fuse` 同源）
   - 今日训练课（M21：默认**不判断**今天练不练，不把星期说成休息日；要课名先
     `keepstrong --type plan`，再用 `steward --slot morning --plan 课名`。
     本周完成课次来自 `coach`；`TRAINING_PLAN` 为空时不判加量）
   - 饮食目标（`PROFILE.macro_targets` / `nutrition`）
   - 待办 Top 3

**禁止**：自己算分、自己估缺口、自己发明课表。

---

## 段 B · 夜间复盘

**触发**：用户投递截图 / 文档 / 文字简报，或说「把今天复盘弄一下」。

**步骤**

1. 跑 `steward --slot evening [归属日]` 看清单（确认日是否已在库）。
2. **整段交给** skill **`daily-review-intake`**（本 skill 不重复其细则）。
3. 回填指引（与 intake 章节对齐，命令见 evening 输出）：
   - 体征 → intake §3.5 → `body`
   - 训练 → intake §3.6 → `keepstrong --date <被复盘日> --write --ingest`
   - 饮食 → intake §3.6 → `nutrition`
   - 学习 → intake §3.7 → `tutor`
4. 收尾：`doctor`（写「七、AI 评价」前看熔断段）；再 `ingest` 兜底 summary。

**禁止**：只进库不落 md；手改四维分；把 ClickUp 习惯勾进「一、日常打卡」。

---

## 段 C · 周度报告

**触发**：用户说「出周报 / 这周怎么样 / 周度总览」。

**步骤**

1. 跑 `steward --slot week <ISO周>`（或给周内某日，由日期推 ISO 周）。
2. 按六段向用户汇报（均可溯源）：

| 段 | 溯源 CLI / 模块 |
| --- | --- |
| 四维 | `week` / `analyze.collect` |
| 体征 | `body` |
| 训练 | `coach` + 周 `training_structure` |
| 饮食 | `nutrition` + 周宏量 |
| 习惯 | `habits` |
| 学习 | `tutor` |

3. 若要落盘结构化周总结骨架：另跑 `week <N> --write`（叙事段仍手写；与 M8 口径一致）。
4. 极值 / 「连续 N 周垫底」等断言**必须脚本复算**，禁止抄旧周报数字。

---

## 与既有资产的边界

| 事 | 谁负责 |
| --- | --- |
| 评分 / 熔断 / 权威归属 | `dailylumen-conventions` |
| 素材 → 当日成品复盘 | `daily-review-intake` |
| ClickUp 归日 / 两套打卡隔离 | `clickup-tracking` |
| 三段编排入口 | **本 skill** + CLI `steward` |

编排输出里若某段为空，如实说「库中无记录 / 请先 ingest」，**不要填默认分**。

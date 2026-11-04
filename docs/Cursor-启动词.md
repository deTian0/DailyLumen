# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-04）：当前阶段 = 深用期（M36–M44）。**
> 完整计划见 **`docs/深用期路线图.md`**；按总览表**下一未完成项**改写下方启动词编号与任务段，
> **别直接沿用旧正文**。运营期（M22–M35）与生活管家（M9–M21）均已完成，仅作历史参考。
> 缺口判定依据见 `docs/能力图谱.md` 的 🔴 / 🟡 清单。

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 换里程碑时按 `docs/深用期路线图.md` 总览表改 **里程碑编号 + 任务段**。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死** —— 这是历史上最容易跑偏的地方
> （曾出现规则文件里的指针停在上一代，导致 Cursor 从错误的里程碑开工）。

---

## 当前里程碑启动词（**M36 · 今日三件事候选**）

> 若 M36 已完成，按深用期路线图下一未完成项改写本节（结构照抄，正文勿沿用）。

```text
你是 DailyLumen 项目的开发搭档。本次会话只做【M36 — 今日三件事候选（FR-A3）】。

项目坐标
- 路径：***REMOVED***\每日复盘计划
- Python：***REMOVED***\.workbuddy\binaries\python\versions\3.13.12\python.exe
- ruff：***REMOVED***/.workbuddy/binaries/python/envs/default/Scripts/ruff.exe
- 分支 main，远端 git@github.com:deTian0/DailyLumen.git（当前 v1.42.0）

动手前先按顺序读完（口径的单一来源，冲突时以它们为准）
1. .cursor/rules/dailylumen.mdc            ← 已自动加载，重点看「硬规则」
2. .workbuddy/skills/dailylumen-conventions/SKILL.md
3. docs/深用期路线图.md 的 §2 全局约束 + §3 通用 DoD + 【M36 那一节】
4. review_tool/pipeline/promise_draft.py（镜像对象）+ skill clickup-tracking / daily-review-intake

背景（立项基线，不是推测）
- 对称 M34 promise-draft（明日 Top 3）；本里程碑面向「今日做成了什么」
- 候选池 = ClickUp 当日已完成任务；落 收件箱/三件事候选-<日期>.md；人勾 ≤3 回填
- 承诺近 30 天仍多天空着；机器只搬运不编造

本次任务（严格照 M36 节，不扩范围）
- 新增 pipeline 模块镜像 promise_draft：当日已完成 → 收件箱草稿（不入库）
- CLI 注册（如 three-things-draft）；intake skill 补勾选回填步骤
- 测试：空候选 / 有完成项 / 草稿不进 ingest / 与明日候选文件名互不覆盖
- 文档：深用期路线图 §1 打勾、设计说明变更日志、版本四处对齐

红线（违反即返工）
- ⛔ 不自动回填复盘正文；与 promise-draft 物理分文件
- ⛔ 零依赖；不改四维评分 / 不动历史分 / 不建定时任务 / 不打开 FEATURES["new_day"]
- ⛔ 不跨里程碑做 M37+

交付要求（DoD，见深用期路线图 §3）
- 全量测试净增且全绿；ruff 干净；版本四处对齐；一个 commit + 一个 tag（v1.43.0）
- 每次写文件后回读校验
- 先别写代码：先读上面材料，说出实施顺序与涉及文件，等我确认后再动手。
```

---

## 历史里程碑启动词（**M16–M19 已完成**，留档参考）

> 下面这几段是已交付里程碑当时的启动词，保留下来是因为「任务块」的写法可以照抄。
> ⛔ 不要再用它们开工 —— 那些里程碑已经完成了。

**M16 · 配置归一化** 的任务块：

```text
本次任务（严格照 M16 节，不扩范围）
- 新增 review_tool/settings.py：@dataclass(frozen=True) + .env 解析 + env 覆盖 + 类型校验
- config.py 改成门面：既有名字（PROFILE / FEATURES / DB_PATH / CLICKUP_LISTS / FOOD_LIB …）
  全部保留，值改为从 SETTINGS 派生 —— 目标是既有 575 项测试零改动全绿
- .env.example 入 git（仓库根，无真实值）；.gitignore 已有 !.env.example 例外
- 新增 tests/test_settings.py；扩展 tests/test_architecture.py 守卫
- ⛔ 零依赖：不许 import pydantic / python-dotenv（架构守卫会拦）
```

**M17 · 练练健身只读接入** 的任务块：

```text
本次任务（严格照 M17 节，只读，不落库）
- 新增 pipeline/keepstrong.py：HTTP 客户端（必需头 / 错误契约 / 分页 / URL 编码 / 缓存）
- 新增 pipeline/keepstrong_render.py：记录 → md 素材（纯函数、零 I/O）
- ROUTES 加 keepstrong 命令：--date / --range / --type records,body,plan / --stdout
- config.py 加 KS_DEFAULTS（baseUrl / skillVersion / agentName / timeout），密钥从 settings 读
- 缓存 .workbuddy/cache/keepstrong-actions.json（非权威，可丢，不入 git）
- 新增 tests/test_keepstrong_client.py、tests/test_keepstrong_render.py（**全离线**，mock urlopen）

接口规格：docs/练练健身-API参考.md（skillVersion 1.28.0，必读，别照记忆写）
红线补充
- ⛔ 本里程碑不调任何写端点、不落库、不改 md，只产 收件箱/keepstrong-素材-<日期>.md
- ⛔ 中文查询参数必须 urllib.parse.quote() —— 实测未编码时返回空 list 且不报错
- 必须实现：401+apiKeyExpired → 停手并指引用户去 App 重新生成 Key；426 → 提示更新技能文档；
  429 → 尊重 Retry-After；绝不紧循环重试
- 中文文案一律写「练练健身」（上游硬要求）
- 素材文件只含数据：不含 API Key、不含 Authorization 头
```

**M18 · 练练数据落 md 并入库** 的任务块：

```text
本次任务（严格照 M18 节，打通 G1，零 schema 迁移）
- 新增 pipeline/keepstrong_sync.py：素材 → 当日 md「附录 · 训练明细」+ 数据块（**幂等**）
- keepstrong --write（默认 dry-run）
- config.KS_ACTION_MAP（练练动作名/actionId → item_key），未命中 slugify 兜底
- 复用 M10 既有表：training_sessions(src='lianlian') / training_items / body_metrics
- 新增 tests/test_keepstrong_sync.py（幂等 / 替换 vs 追加 / 空数据）

红线补充
- ⛔ G1：练练数据先落 md → 再 ingest。禁止「只进库不落 md」
- ⛔ 幂等：同一天重复同步 = 替换该日「来源：练练」段落，不是追加第二份；人工手写的明细不动
- ⛔ R2：exercise_min 仍是健康分唯一运动输入；durationSeconds 只在字段为空时派生填入（标 derived），不叠加
- 验收必须实跑：对 2026-10-01（练练里有记录）同步 → ingest → 再同步一次 → 断言 md 与库均无重复行
```

---

## 通用模板（换任何里程碑都适用）

```text
你是 DailyLumen 项目的开发搭档。本次会话只做【M__ — <主题>】。
先读：.cursor/rules/dailylumen.mdc → .workbuddy/skills/dailylumen-conventions/SKILL.md
      → docs/深用期路线图.md 的 §2 / §3 / 【M__ 那一节】
红线：零依赖 / 不改四维评分 / 不建定时任务 / 配置分层 / 新数据先落 md 再入库
DoD：测试全绿 + ruff 干净 + 版本四处对齐 + 一个 commit + 一个 tag + 写盘回读校验
先别写代码，先说实施顺序与涉及文件，等我确认。
```

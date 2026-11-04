# Cursor 启动词（贴进 Cursor 对话的第一段话）

> ⚠️ **状态（2026-11-04）：深用期（M36–M44）已全部完成（收尾 v1.50.1）。**
> **待下一阶段** —— 新需求先写进新的阶段路线图再开工；历史计划见
> `docs/深用期路线图.md`（M36–M44 ✅）/ `docs/运营期路线图.md`（M22–M35 ✅）/
> `docs/生活管家路线图.md`（M9–M21 ✅）。
> 缺口判定依据见 `docs/能力图谱.md` 的 🔴 / 🟡 清单。

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 下一阶段立项后，按新路线图总览表改 **里程碑编号 + 任务段**。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死** —— 这是历史上最容易跑偏的地方
> （曾出现规则文件里的指针停在上一代，导致 Cursor 从错误的里程碑开工）。

---

## 当前里程碑启动词（**待下一阶段**）

> 深用期无未完成项。下一阶段立项前，不要沿用历史里程碑正文开工。

```text
你是 DailyLumen 项目的开发搭档。当前深用期（M36–M44）已全部完成（v1.50.1）。
本次会话不要擅自开新里程碑；若有新需求，先更新下一阶段路线图再动手。

项目坐标
- 路径：***REMOVED***\每日复盘计划
- Python：***REMOVED***\.workbuddy\binaries\python\versions\3.13.12\python.exe
- ruff：***REMOVED***/.workbuddy/binaries/python/envs/default/Scripts/ruff.exe
- 分支 main，远端 git@github.com:deTian0/DailyLumen.git（当前 v1.50.1）

动手前先按顺序读完
1. .cursor/rules/dailylumen.mdc
2. .workbuddy/skills/dailylumen-conventions/SKILL.md
3. docs/能力图谱.md（缺口）+ docs/深用期路线图.md（已完成历史）
4. 若用户已给出下一阶段路线图，只做其中「下一未完成项」

红线
- ⛔ 零依赖；不改四维评分 / 不动历史分 / 不建定时任务 / 不打开 FEATURES["new_day"]
- ⛔ 不跨里程碑混提交；一次只做一个已立项里程碑
```

---

## 历史里程碑启动词（**M36 深用期首项 · 已完成**，留档参考）

> ⛔ 不要再用它开工 —— M36–M44 已全部交付。结构可照抄到下一阶段启动词。

```text
你是 DailyLumen 项目的开发搭档。本次会话只做【M36 — 今日三件事候选（FR-A3）】。
（完整任务块见 git 历史 v1.42.0 时期启动词；已交付 v1.43.0。）
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
      → 下一阶段路线图（若已立项）的 §2 / §3 / 【M__ 那一节】；否则先读 docs/能力图谱.md
红线：零依赖 / 不改四维评分 / 不建定时任务 / 配置分层 / 新数据先落 md 再入库
DoD：测试全绿 + ruff 干净 + 版本四处对齐 + 一个 commit + 一个 tag + 写盘回读校验
先别写代码，先说实施顺序与涉及文件，等我确认。
```

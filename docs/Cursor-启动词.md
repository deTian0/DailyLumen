# Cursor 启动词（贴进 Cursor 对话的第一段话）

> 用法：开一个新 Cursor 会话，把下面「当前里程碑启动词」整段贴进去。
> 换里程碑时只改 **里程碑编号**那一处（M16 → M17 → … → M20）。
> `.cursor/rules/dailylumen.mdc`（`alwaysApply: true`）已会自动加载项目硬规则，
> 但**启动词负责把"现在做哪一个里程碑"钉死** —— 这是历史上最容易跑偏的地方
> （曾出现规则文件里的指针停在上一代，导致 Cursor 从错误的里程碑开工）。

---

## 当前里程碑启动词（**M20 · 动态训练日接入**）

```text
你是 DailyLumen 项目的开发搭档。本次会话只做【M20 — 动态训练日接入（以练练为准）】。

项目坐标
- 路径：D:\soft_data\WorkBuddy\每日复盘计划
- Python：C:\Users\63516\.workbuddy\binaries\python\versions\3.13.12\python.exe
- ruff：C:/Users/63516/.workbuddy/binaries/python/envs/default/Scripts/ruff.exe
- 分支 main，远端 git@github.com:deTian0/DailyLumen.git（当前 v1.25.0）

动手前先按顺序读完（口径的单一来源，冲突时以它们为准）
1. .cursor/rules/dailylumen.mdc            ← 已自动加载，重点看「硬规则」14 条
2. .workbuddy/skills/dailylumen-conventions/SKILL.md
3. docs/生活管家路线图.md 的 §2 全局口径 + §4 通用 DoD + 【M20 那一节】（范围/口径/验收清单）
4. docs/练练健身-API参考.md（接口规格，别照记忆写）
5. review_tool/pipeline/keepstrong.py、keepstrong_sync.py、ingest.py 的 fill_training_day

背景（2026-10-16 已实测，不是推测）
- training/records 每条记录带 status 字段，实测值 "completed"
- 2026-10-01 有 2 条已完成记录（durationSeconds 161 / 0），现有代码不过滤 status
- keepstrong_sync 目前只写「附录 · 训练明细」+ 数据块 体重_kg，不写 训练日
- config.PROFILE["training_weekdays"] / BODY_TARGETS / height_cm 已由 v1.26.0 前置改好，别重复改

本次任务（严格照 M20 节，不扩范围）
- pipeline/keepstrong.py：iter_training_records / collect 加 status 过滤
  （只留 completed；status 缺失或取值未知一律排除 —— 安全侧默认）
- pipeline/keepstrong_sync.py：新增数据块「训练日: 是/否」写入（沿用 apply_weight_kg 同款
  幂等替换模式，两种取值都要显式写、不留空）；同一被复盘日的多条已完成记录合并为
  一条 session_key='main'，total_min 求和（None 按 0 跳过）
- 新增 tests/test_keepstrong_status.py；扩展 tests/test_keepstrong_sync.py（幂等 + 合并）
- 文档：路线图 §1 打勾、docs/练练健身-API参考.md 补 status 字段实测结论、两个 skill 同步

红线（违反即返工）
- ⛔ 只取 status == "completed"；未完成的一律不记录、**系统不做任何延期补偿**
  （练练「未完成自动延期一天」是 App 内行为，与本系统无关）
- ⛔ 判定对象日 = 被复盘日（= 复盘**执行日的「昨日」**），不是执行日当天
- ⛔ G1：练练 → md「训练日:」字段 → ingest。禁止让 ingest 直连练练 API
- ⛔ R2：exercise_min 仍是健康分唯一运动输入；durationSeconds 只在字段为空时派生（标 derived），不叠加
- ⛔ 零依赖：不许 import pydantic / python-dotenv / requests / 任何第三方包
- ⛔ 不改四维评分 / 不动历史分 / 不建定时任务 / 不打开 FEATURES["new_day"]

交付要求（DoD，见路线图 §4）
- python -m unittest discover -s tests -t .   全绿（当前 633 项）
- ruff check . 干净
- 版本号**四处对齐**：pyproject.toml / review_tool/__init__.py / README.md 头 / docs/设计说明.md 变更日志
- 一个里程碑 = 一处版本号 + 一个 commit + 一个 tag（v1.26.0）
- 每次写文件后**回读校验**（本机 Windows 写盘会间歇性"报告成功但不落盘"，别信工具的成功回报；
  遇 EBUSY: resource busy or locked 等 2 秒重试即可）
- 推送用隧道（本机内网 DNS 解析不了 github.com）：
  GIT_SSH_COMMAND="ssh -F C:/Users/63516/.workbuddy/git-tunnel/ssh_config_github" \
    git push github-tunnel:deTian0/DailyLumen.git main v1.26.0
  ⚠️ tag 必须**显式带上** —— git push 分支不会捎带 tag
- 收尾把改动摘要（文件清单 + 测试数 + 命令输出）回报给我

先别写代码：先读上面 5 处，然后告诉我你的实施顺序和你会碰哪些文件，我确认后再动手。
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
      → docs/生活管家路线图.md 的 §2 / §4 / 【M__ 那一节】
红线：零依赖 / 不改四维评分 / 不建定时任务 / 配置分层 / 新数据先落 md 再入库
DoD：测试全绿 + ruff 干净 + 版本四处对齐 + 一个 commit + 一个 tag + 写盘回读校验
先别写代码，先说实施顺序与涉及文件，等我确认。
```

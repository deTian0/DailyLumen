---
name: clickup-tracking
description: ClickUp 是 DailyLumen 的「行为跟踪执行层」。本 skill 定义 ClickUp 空间结构与 list ID 速查、凭据与命令行入口、ClickUp 数据 → 复盘素材的映射口径、日期归属规则（用 date_closed 而非 due_date）、以及「两套打卡体系不许混」的边界。触发词：ClickUp、行为跟踪、习惯同步、日常事务、年度目标、阅读体系、cu.bat、clickup_client、从 ClickUp 拉记录出复盘。
agent_created: true
---

# ClickUp 行为跟踪 ↔ DailyLumen 复盘

> **分工先记死**：**ClickUp = 执行层**（我今天干了什么、有哪些待办）；
> **DailyLumen = 评价层**（这一天值几分、要不要熔断）。
> 两者之间只做**单向的素材供给**（ClickUp → 复盘）；ClickUp **不直接决定任何分数**。

## 0. 三条边界（先看这个）

**① ClickUp 不参与评分。** 四维分只由 `config.SCORE_THRESHOLDS` 规则 + 复盘 md 的数据块决定。
ClickUp 只提供「当日行为证据」，是否写进 md 由复盘流程判断。

**② 两套打卡体系，绝对不许混。**

| 体系 | 载体 | 内容 | 落到哪 |
| --- | --- | --- | --- |
| **个人打卡项** | 复盘 md「一、日常打卡」的 `- [x]` 勾选 | **补剂 / 护肤**（定义在 `config.PERSONAL_ITEMS`） | `personal_tracks` 表，可算依从率 |
| **ClickUp 习惯** | ClickUp「习惯与打卡」list | **行为习惯**（阅读 / 健身 / 背单词…） | ⛔ **不落库**，只当素材看 |

⛔ 别因为 ClickUp 勾了「每日阅读 30 分钟」就往 md 的「一、日常打卡」补一行 ——
那不属于补剂/护肤，会污染依从率，`doctor [打卡对账]` 会立刻报出来。

**③ 日期看 `date_closed`，不看 `due_date`。**
`due_date` 是**计划日**，`date_closed` 才是**实际完成时刻**。
统计「某天完成了什么」必须按 `date_closed` 落在目标日（东八区）过滤 —— 用 `due_date` 会把
「今天做完的昨天到期任务」判成昨天，把「今天到期但明天才做」判成今天。

---

## 1. 凭据与入口（本机）

- **凭据**：`~/.workbuddy/mcp.json` → `mcpServers.clickup.env.CLICKUP_API_KEY` / `CLICKUP_TEAM_ID`
  （环境变量同名可覆盖，优先于文件）。
  🔴 **token 绝不写进本仓库任何文件** —— 本仓库入 git。skill 运行时现读。
- **Workspace / Team ID**：`9014643172`（Detian's Workspace）——
  注意 token 里那串 `156108067` 是**用户 ID，不是 Team ID**。
- **命令行入口**：`~/.workbuddy/clickup-tools/clickup_client.py`
  - 解释器写在同一目录 `python_path.txt`（本机 = 托管 Python 3.13）；双击入口是同目录 `cu.bat`。
  - 该客户端**只用标准库**，不需要任何 pip 包。
- **通用 API 能力**（批量建任务 / 跨 list 迁移 / 20+ 踩坑清单）见**用户级 skill**
  `clickup-api-bulk-tasks`。本 skill 只讲**与复盘系统的衔接**。

---

## 2. 空间结构速查（2026-10-13 重组后）

| 层级 | 名称 | ID | 形态 |
| --- | --- | --- | --- |
| Space | ls 的空间 | `90142766516` | — |
| Folder 生活 | 日常事务 | `901422213138` | 每日流水（含「每日复盘总结-YYYY年M月D日」这类元任务） |
| Folder 生活 | 习惯与打卡 | `901422213139` | 6 条长期习惯，见下 |
| Folder 成长 | 成长课 · 14周计划 | `901422213140` | 阶段式课程 + 循环节奏任务 |
| Folder 成长 | 阅读与学习 | `901422213142` | 8 大类 56 本书单（按标签分类） |
| 顶层 | 工作 | `901410092299` | 工作事项 |
| 顶层 | 项目孵化 | `901422213132` | 想法 / 待孵化 |
| 顶层 | 2026 年度目标 | `901422213133` | 12 个 Flag（父任务「计划-2026Flag」+ 11 子任务） |
| Space | 个人 | `90144434151` | 空 |

> ⚠️ **list 清单有两处，改要一起改**：本文是**口径与语义**的来源；代码侧的采集清单在
> `review_tool/config.py` 的 `CLICKUP_LISTS`（`clickup` 子命令按它取数，`daily=True` 为默认每日来源）。
> 新增 / 归档 list 时两处同步，否则「文档里有、命令不采」或反过来。

**「习惯与打卡」6 条**：每日阅读 30 分钟 / 练练健身 / 整理随手记app数据 / 每日复盘总结 /
墨墨背单词app / 寻找一些个人提升的好习惯，然后调整自己。

**已归档**（`PUT /list/{id} {"archived":true}`，可 Unarchive 还原，不占侧栏）：
日常 `901417513334`、任务 `901410092337`、想法 `901410129541`、旧成长课 `901422212593`。
⚠️ 读归档 list 的任务要传 **`archived=false`**（传 `true` 会返回空数组，看着像数据全丢）。

---

## 3. 映射口径：ClickUp → 复盘

| ClickUp 来源 | 能证明什么 | 落到复盘的位置 | 流向 |
| --- | --- | --- | --- |
| 日常事务 · 当日完成项 | 今天具体做了什么 | 「二、今日三件事」的素材候选 | 只读 |
| 习惯与打卡 · 完成情况 | 长期习惯的连续性 | 「五、时间投入」佐证 / 「七、AI 评价」趋势描述 | 只读，**不落库** |
| 成长课 · 14周计划 | 学习进度 | `学习投入_h` 的证据 | 只读 |
| 阅读与学习 | 读书进度 | `学习投入_h` 的证据 | 只读 |
| 工作 / 项目孵化 | 工作产出 | `深度工作_h` 的证据 | 只读 |
| 2026 年度目标 | 长期方向 | 「四、明日 Top 3」的对照锚点 | 只读 |

**唯一允许的写方向**：用户明确要求时（「帮我把这条记进 ClickUp」），
用 `add` / `done` 写 ClickUp —— 但**不等于**改动复盘系统，两者仍各自记账。
写操作后一律 `GET` 回读确认（ClickUp 有「返回 200 但静默忽略」的已知行为）。

---

## 4. 取「某天完成了什么」（复盘时的标准动作）

**首选：直接跑项目自带命令**（v1.6.0 起，取数已代码化 —— 别再手写脚本）：

```bash
python -m review_tool clickup 2026-10-13            # 落 每日复盘/收件箱/clickup-素材-2026-10-13.md
python -m review_tool clickup 2026-10-13 --stdout   # 只看不落文件
python -m review_tool clickup --list 901422213142   # 换一批 list（可重复，也可逗号分隔）
```

- 默认采 `config.CLICKUP_DAILY_IDS`（日常事务 + 习惯与打卡）；改范围改 `config.CLICKUP_LISTS`。
- 它**已经替你处理**了三个坑：按 `date_closed` 归日（东八区）、带 `include_closed=true`、
  按 id 去重 **+ 翻页**（单页 100，不翻页会静默漏）。
- 产出是**素材**（落 `收件箱/`，不参与 ingest 扫描），**不是**复盘成品；同一分钟 ≥10 条完成
  时素材会自带「疑似批量改状态」提示，别把那数字读成「一口气干了 N 件事」。
- 退出码：`0` 成功 / `1` 取数失败（网络 / 认证）/ `2` 用法或凭据问题。

**临时查别的维度**（命令没覆盖的）才手写脚本，但下面这条口径必须守死：
先拉全量（**必须带 `include_closed=true`**，否则已完成任务全漏），
再按 `date_closed` 落在目标日过滤，最后按 list 分组。

```python
import json, datetime, urllib.request, os

KEY = json.load(open(os.path.expanduser('~/.workbuddy/mcp.json'), encoding='utf-8-sig')) \
          ['mcpServers']['clickup']['env']['CLICKUP_API_KEY']
TZ = datetime.timezone(datetime.timedelta(hours=8))
DAY = '2026-10-14'          # 目标日

def day_of(ms):             # ClickUp 的毫秒时间戳 -> 东八区日期串
    return datetime.datetime.fromtimestamp(int(ms) / 1000, TZ).strftime('%Y-%m-%d')

def get(path):
    r = urllib.request.Request('https://api.clickup.com/api/v2' + path)
    r.add_header('Authorization', KEY)
    with urllib.request.urlopen(r, timeout=60) as resp:
        return json.loads(resp.read().decode('utf-8'))

for lid in ['901422213138', '901422213139']:        # 日常事务 / 习惯与打卡
    ts = get('/list/%s/task?subtasks=true&include_closed=true&page=0' % lid).get('tasks', [])
    hit = [t for t in ts if t.get('date_closed') and day_of(t['date_closed']) == DAY]
    print('== list %s  当日完成 %d 条 ==' % (lid, len(hit)))
    for t in hit:
        print('  -', t['name'])
```

---

## 5. 常用命令

```bash
# ① 复盘取数（首选，走项目自带管道；只读、不落库、不参与评分）
cd <仓库根> && python -m review_tool clickup 2026-10-13          # → 收件箱/clickup-素材-<日期>.md
python -m review_tool clickup --stdout                           # 只看不落文件（默认今天）

# ② 直接问 ClickUp（临时查 / 写操作）
PY=$(cat ~/.workbuddy/clickup-tools/python_path.txt)
CLI=~/.workbuddy/clickup-tools/clickup_client.py
$PY $CLI whoami                      # 确认连得上（认证失败 = token 失效/已轮换）
$PY $CLI tree                        # 整个工作区结构
$PY $CLI ls 901422213138 --all       # 看某个 list（--all = 含已完成）
$PY $CLI show <task_id>              # 单条任务详情
$PY $CLI add 901422213138 "任务名" --due 2026-10-20 --tags 生活 --priority 3
$PY $CLI done <task_id>              # 标完成（写后会回读 status）
$PY $CLI archive <list_id>           # 归档 list（可 Unarchive 还原）
```

---

## 6. 坑（复盘场景高发的几条）

| 坑 | 表现 | 处理 |
| --- | --- | --- |
| 拉不到已完成任务 | 只拿到几条，看着像「今天什么都没干」 | 必须带 `include_closed=true`；`subtasks=true` 分页会**重复返回**，按 `id` 去重 |
| 用 `due_date` 判完成日 | 今天的完成项被算到昨天 / 明天 | 用 `date_closed` |
| 归档 list 返回空 | 以为数据全丢 | 传 `archived=false`（不是 `true`） |
| 写操作 200 但没生效 | 移动类字段被静默忽略 | **一律 GET 回读确认**，不信状态码 |
| 限流 | 免费版 100 次/分 | 批量间隔 0.25s |
| 中文标签名进 URL 崩 | `UnicodeEncodeError` | 路径里的自定义名过 `urllib.parse.quote()` |
| 日期传字符串 | `{"err":"Date invalid","ECODE":"INPUT_006"}` | 一律 Unix **毫秒整数** |

---

## 7. 安全

- `pk_` token **长期有效、能读写整个 Workspace**。本机副本在 `~/.workbuddy/mcp.json`（明文）。
  - 一旦出现在对话 / 截图 / 公开文件里 → 到 ClickUp 后台 `Settings → Apps` 重新生成，
    然后更新 mcp.json（两台机器要**一起换**，否则一台 401）。
  - 迁移包（含明文 key 的 zip / 文件夹）装完即删。
- 本 skill 及其所在仓库**不含 token**；引用凭据一律走 `~/.workbuddy/mcp.json`。

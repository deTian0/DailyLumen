# 练练健身（KeepStrong）AI 接口参考

> **来源**：`GET https://lianlian.gzyunke.cn/api/v1/ai/skill`（Bearer 认证）
> **文档版本**：**1.28.0** ｜ 拉取日期：2026-10-15
> **本文用途**：开发时的接口规格单一来源。**不含任何密钥** —— API Key 只存在于本机 `.env`。
> **上游约定**：`skillVersion` 变更时服务端返回 `HTTP 426 + skillUpdateRequired=true`，
> 需重新拉取上文 URL 并替换本文件（`skillUrl` 字段给出新地址）。

---

## 1. 认证与必需请求头

| 头 | 值 | 说明 |
| --- | --- | --- |
| `Authorization` | `Bearer <API_KEY>` | Key 从本机 `.env` 的 `KEEPSTRONG_API_KEY` 读，**永不入 git / 日志 / 报告** |
| `X-KeepStrong-Skill-Version` | `1.28.0` | **除拉 skill 文档外的每个请求都要带**；426 时更新 |
| `X-KeepStrong-Agent-Name` | 稳定的 ASCII 产品名（如 `WorkBuddy`） | 必带；⛔ 不要用模型名 / 版本号 / 用户名 |
| `X-Timezone-Offset` | `480` | **分钟，东为正**。中国 = 480。JS 的 `getTimezoneOffset()` 符号相反，需取反 |
| `Idempotency-Key` | 唯一字符串 | **每个写请求必带**；同一次逻辑请求重试才复用同一个 key |
| `Content-Type` | `application/json` | 写请求 |

**日期格式一律 `yyyyMMdd`**（如 `20261015`）。

---

## 2. 错误处理契约（必须实现）

| 状态 | 含义 | 处理 |
| --- | --- | --- |
| `401` + `apiKeyExpired=true` | Key 失效 | **停止重试**。让用户去 练练健身 > 我的 > 连接 AI → 生成新 Key → 复制 AI 连接信息 → 贴回对话。等新凭据再继续 |
| `426` + `skillUpdateRequired=true` | 技能文档过期 | 重新拉 `skillUrl`，替换本文档，用新版本号重试 |
| `429` | 限流 | 按 `Retry-After` 等待，**绝不紧循环重试** |
| `409` | 并发同 key | 换新的 `Idempotency-Key` 重发（写请求） |
| 日期错误 `TIMEZONE_OFFSET_SIGN_MISMATCH` | 时区符号错 | **保持 dayStr 不变**，改正 `X-Timezone-Offset`，换新 key 重试。别怀疑服务器时钟 |

---

## 3. 读端点（本次接入范围）

| 方法 | 路径 | 参数 | 返回要点 |
| --- | --- | --- | --- |
| GET | `/api/v1/ai/training/records` | `startDate, endDate, page, pageSize<=50` | 力量 / 计划 / 手动 / 外部导入四类记录；**每条含 `status`**（见 §5） |
| GET | `/api/v1/ai/training/running-plans` | — | 跑（训练）计划 + 日程 + 今日课 + 循环设置 |
| GET | `/api/v1/ai/training/actions` | `keyword, page, pageSize<=200` | 动作库搜索 |
| GET | `/api/v1/ai/training/actions/{actionId}/history` | `startDate, endDate, page, pageSize<=50` | 单个动作的组 / 次 / 重量历史 |
| GET | `/api/v1/ai/training/templates` | `page, pageSize<=50` | 用户动作模板 |
| GET | `/api/v1/ai/food/logs` | `dayStr`（**最近 60 天、一次一天**） | 当日饮食 + 运动消耗；含 `exerciseCost` |
| GET | `/api/v1/ai/food/search` | `keyword, pageSize<=30`（日限 100） | 食物搜索（仅 name + 营养/100g） |
| GET | `/api/v1/ai/food/favorites` | `page, pageSize<=100`（默认 20） | 收藏食物 |
| GET | `/api/v1/ai/food/my-foods` | `page, pageSize<=100`（默认 20） | 自建食物（含 AI 建的私有食物） |
| GET | `/api/v1/ai/body/profile` | — | 身高 / 当前体重 / 体脂 / 可用围度类型 |
| GET | `/api/v1/ai/body/logs` | `metric=weight\|fat\|bodyRound, bodyType?, startDate, endDate, page, pageSize<=100`（**最近 3 年**） | 体重 / 体脂 / 围度记录；**同一天保留最新一条** |

> 分页：一律跟 `hasMore`；**不要超过各端点的 pageSize 上限**。
> 缓存：动作库结果（尤其 `actionId` + `name`）宜本地缓存复用，避免同一动作反复搜索。

---

## 4. 写端点（M19 才做，且必须显式确认）

| 方法 | 路径 | 关键字段 |
| --- | --- | --- |
| POST | `/api/v1/ai/training/scheduled-workouts` | `userConfirmed=true, dayStr, name, actions` |
| POST | `/api/v1/ai/training/actions/{actionId}/weight` | `userConfirmed=true, weight`（**绝对重量，非增量**）, `rightWeight?, weightUnit?, templateId?` |
| POST | `/api/v1/ai/training/templates` | `userConfirmed=true, name, actions, templateId?` |
| POST | `/api/v1/ai/training/templates/{templateId}/actions` | `userConfirmed=true, actions`（**完整替换**） |
| POST | `/api/v1/ai/training/custom-plans` | `userConfirmed=true, name(<=15字), schedules`（**整个循环一次提交**） |
| POST | `/api/v1/ai/training/running-plans/{runningPlanId}/workouts` | `userConfirmed=true, actions, dayStr?, templateId?` |
| POST | `/api/v1/ai/training/running-plans/{runningPlanId}/commands` | `userConfirmed=true, command` ∈ {delay, cancel_rest, add_alternative, add_temporary_workout} |
| POST | `/api/v1/ai/food/logs` | `userConfirmed=true, dayStr, mealKey, foods\|exercises`（**每条食物必须有 grams**，0.1–100000） |
| POST | `/api/v1/ai/body/logs` | `userConfirmed=true, metric, value, unit, dayStr` |

**写入硬约束（上游明确要求）**

1. **写前必须把完整变更展示给用户并获得明确确认**；工作训练要逐条列出日期 / 课名 / 每个动作 / 组 / 次 / 重量。
2. 确认后**才**发请求，并带 `userConfirmed=true`；**变更内容一变就要重新确认**。
3. 未指定重量时传 **`weight=""`（空串）**，让 App 自动沿用历史重量；**⛔ 绝不用 `0` 占位**（`0` 会关闭自动取值）。
4. 写成功后要**照着返回体核对**（`actionId` / `templateId` / `weight` / `weightUnit`），并提醒用户「App 里没立刻变化可能需重启」。
5. **绝不谎报成功**；失败要如实报告。
6. 只允许**用户明确要求**时才调写端点。

**练习结构语法**（写模板 / 计划时）

- 递变组（drop set）：普通 group 上加 `dropSets`（1–10 级）
- 超级组（superset）：一个 action 里放 `supersetActions`（2–4 个动作，**组数必须相同**）
- ⛔ 超级组内不支持递变组
- 热身组：`warmupGroup` 里带 `flag="hot"`；热身组不能再含 dropSets
- `restSeconds` / `weightUnit` / `creatorTip`（≤300 字符，动作级提示）为可选

---

## 5. 本账号实测快照（2026-10-15 · 实测非推测）

| 端点 | 实测结果 |
| --- | --- |
| `training/records` 20260101–20261015 | ✅ 有记录（如 `20261001` strength，`durationSeconds=161`，`calorie=9`，`actions: []`） |
| `training/records` **`status` 字段**（2026-10-16 再测） | ✅ 每条记录带 **`status`**；实测值为 **`"completed"`**。样本：`{"id":"temp:bqf4tB1Ajd",…,"status":"completed","dayStr":"20261001","durationSeconds":161,…}`。DailyLumen **只取 `completed`**（M20）；缺失 / 未知取值一律排除，不做延期补偿 |
| `training/records` 同日多条（2026-10-01） | ✅ 两条 completed：`161s` + `0s` → 合并后 `total_min=3`（`seconds_to_min(161)=3`，`0→None` 跳过） |
| `training/records` 20261008–20261015 | ⚠️ **空** —— 与复盘「训练日连续挂零」互相印证，**不是数据缺失** |
| `training/running-plans` | ✅ 存在计划「一分化」`planId=9vMyLd`，6 天循环：全身A / 休息日 / 全身B / 休息 / 全身C / 空 |
| `training/actions` | ✅ 可用；`act_` + 24 位十六进制（如 `act_0ef816635ec333cfc6bf0527` 壶铃深蹲） |
| `training/templates` | 空（本账号未用模板功能） |
| `body/profile` | ✅ `weight=82kg`（`weightSource=bodyLog`, `dayStr=20260920`）；`height=null`；`fat=null`；围度类型 8+（biwei/xiongwei/yaowei/tunwei/jianwei/xiaotuiwei…） |
| `body/logs?metric=weight` | ⚠️ 仅 1 条（2026-09-20, 82kg） |
| `food/logs?dayStr=20261014` | ⚠️ 端点可用但**当日为空**（用户饮食记在薄荷，不记练练） |

**由此确定的数据源分工**：练练 = **运动主数据源**；饮食 / 睡眠 / 屏幕仍走薄荷与小米截图。

---

## 6. 实测踩坑（写代码前先看）

| 坑 | 表现 | 解法 |
| --- | --- | --- |
| **中文 keyword 未编码** | `actions?keyword=深蹲` → **空响应**（不报错，最容易误判成"没这个动作"） | 查询参数一律 `urllib.parse.quote()` |
| `food/logs` 一次只能一天 | 传日期范围无效 | 循环单天调用；且**只覆盖最近 60 天** |
| `body/logs` 时间窗 | 超出范围返回空 | 仅最近 **3 年** |
| `weight=0` 语义 | 会**关闭**自动沿用历史重量 | 未指定时传空串 `""` |
| 记录 `actions` 可能为空 | 临时训练（`trainingType=temp`）只给时长/热量 | 别假定有动作明细；空明细是合法输入 |
| 写端点无 dry-run | 报错发生在保存**之前**，超时却可能在保存**之后** | 不定状态去 App 里核对，别盲目重试 |

---

## 7. 与 DailyLumen 的口径衔接（**本项目自己的约定**）

1. **练练是「输入通道的自动化升级」，不是新的权威源** —— 与截图同级、但更可靠。
   数据必须**先落 md 附录 → 再 `ingest`**，保住 G1「删库可从 md 100% 重建」。
2. **⛔ 禁止「只进库不落 md」** —— 会破掉可重建性。
3. 落库目标复用既有表（**零 schema 迁移**）：
   - 训练 → `training_sessions` / `training_items`（`src='lianlian'`，**M10 已预留该枚举值**）
   - 体重 / 体脂 → `body_metrics`（`src='scale'` 或 `manual`）
4. **R2 不破**：`exercise_min` 仍是健康分的唯一运动输入；练练的 `durationSeconds` 只在
   字段为空时用于填 `运动时长_min`（标 `derived`），**不与已有字段叠加**。
5. **训练日（M20 / v1.26.0）**：只认 `status == "completed"` → md `训练日: 是/否` → ingest；
   API 失败不写「否」（留给 `training_weekdays` 离线兜底，CLI 明示）。
6. 动作库缓存是**纯性能缓存**（丢了能重拉）→ 不算「无法从 md 重建的状态」，放
   `.workbuddy/cache/`（不入 git）。
7. 写回练练（POST）是**外部副作用**：只在用户明确要求时执行，**不落库、不作系统状态**。

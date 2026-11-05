---
name: llm-host-contract
description: DailyLumen 宿主（WorkBuddy/Cursor）读图填数与写「七、AI」的短契约——字段表、拒估规则、落盘 checklist。mode=workbuddy 时加载；无 HTTP API。触发词：宿主契约、读图填数、七AI草稿、拒估、llm-host-contract。
agent_created: true
---

# 宿主 LLM 契约（短片段 · 供对话引用）

> **正文权威**仍在 [`docs/LLM能力拆分草案.md`](../../../docs/LLM能力拆分草案.md) **§4**。  
> 本 skill 只给**可粘贴的短表**；流程步骤见 `daily-review-intake`。  
> ⛔ **没有** WorkBuddy / 宿主 HTTP API 或 SDK 可供本仓库调用；`mode=workbuddy` = 你在对话里履约后写 md。

## 字段表（通道 A · 数据块）

| 组 | 契约键（中文） | 备注 |
| --- | --- | --- |
| 饮食 | `饮食热量_kcal` `碳水_g` `脂肪_g` `蛋白质_g` `三餐情况` `早餐按时` | 看不清就省略 |
| 体征 | `体重_kg` `体脂率` `腰围_cm` | 均可选；**`体脂率` 无设备可永久跳过**，⛔ 禁止伪造 |
| 睡眠 | `睡眠时长_h` `睡眠质量` `入睡时间` | 醒来日口径 |
| 活动 | `手机屏幕_h` `运动时长_min` `训练日` | 训练日以练练 completed 为准（另通道） |

英文别名可映射（如 `diet_kcal`→`饮食热量_kcal`）；未知键勿硬写进数据块。

## 拒估规则（写死）

1. ⛔ **缺失留空合法**——不要为「看起来完整」估算屏幕 / 睡眠 / 热量 / **体脂**。  
2. ⛔ **禁止只进库**——只写当日复盘 md（数据块 / 附录 /「七、AI」），再 `ingest`。  
3. ⛔ **不手改「六、四维评分」分数**；不编造上下文未列出的数字（含体脂率）。  
4. ⛔ **没提打卡 ≠ 做了**；口述流水不产数据块数值。  
5. ⛔ **不要调用** `llm-review` / `llm-vision` / `llm-day`（除非用户已设 `DAILYLUMEN_LLM_MODE=deepseek`）。

## Checklist（宿主一次履约）

- [ ] 确认对象日（当晚写当天）  
- [ ] 截图 / 口述 → 填数据块或附录（缺项空着）  
- [ ] `python -m review_tool ai-context <日>` + 看 `doctor` 熔断 / 相对基线  
- [ ] 建议段挂 `life-decision-guide`（人勾选才落改进点）  
- [ ] 撰写「七、AI」→ 可先七-A 草稿；人审后 `llm-finalize <日> --write`（或手清 pending / 七-B）  
- [ ] `ingest`（未定稿会被跳过）→ `finalize --apply`（分数收口；≠ `llm-finalize`） 

## deepseek 对照（非本 skill 主路径）

```text
python -m review_tool llm-day --image A.png --image B.png --date YYYY-MM-DD [--review] [--diff]
# 或分拆：
python -m review_tool llm-vision --image A.png --image B.png --date YYYY-MM-DD [--diff]
python -m review_tool llm-review YYYY-MM-DD [--diff] [--write]
```

多图合并：**后图非空覆盖先图**，冲突记入结果 / 日志。产出仍先 md；摘要可落 `local/llm_last_run.json`（无密钥）。

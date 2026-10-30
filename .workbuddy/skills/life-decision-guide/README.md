# life-decision-guide（项目内副本）

《高性价比人生指南》决策 skill 的仓库内副本。**规则的真源是同目录的 [SKILL.md](SKILL.md)**，
本文件只写「在这个仓库里怎么装、怎么加载、怎么升级」，不重复任何决策规则。

上游：<https://github.com/eternity4719/HowToLiveBetter>（`skills/life-decision-guide/`）

## 为什么放在这个仓库

复盘回答的是「今天做了什么」，这个 skill 回答的是「这件事到底该不该做」——两者共用同一套
成本 / 收益 / 证据等级的账。把规则随代码入库，换机 clone 下来就能用，不依赖某台机器的用户目录。

目录内共两个文件：

| 文件 | 作用 | 能不能改 |
| --- | --- | --- |
| `SKILL.md` | 唯一真源，决策规则全在这里 | 只改「本机补丁」那三处，其余保持与上游一致 |
| `README.md` | 本文件，仓库侧运维说明 | 随便改 |

## 怎么加载

WorkBuddy 扫的是 `<工作区>/.workbuddy/skills/<name>/SKILL.md`，靠 frontmatter 的 `name` + `description`
建索引，**description 常驻、正文按需载入**。所以本文件放对位置就自动生效，不需要注册到任何配置。

三种触发方式：

1. **自动**：`description` 里带触发词（该不该 / 值不值 / 要不要 / 划不划算 / 怎么选 / 帮我决定 /
   这样犯法吗 / 能领什么 / 先做什么 / 性价比）。提到这些就按需载入正文。
2. **显式点名**：「用 life-decision-guide 回答」「按人生决策 skill 答」。
3. **斜杠**：工作区 skill 在本会话可直接调用，名称即 `life-decision-guide`。

⚠️ **新建的 skill 在旧会话里看不到**——skill 清单是会话启动时的快照。装完或改完 description，
**开一个新会话**再验证；本会话内只能靠显式点名或直接读 `SKILL.md`。

### 本机额外有一条用户级捷径

`C:\Users\63516\.workbuddy\skills\life-decision-guide` 是指向本目录的 **junction**（不入 git）。
作用是在别的项目里也能用同一个 skill。因为是同一份文件，**改这里两边同时生效，不存在漂移**；
换机后 junction 不存在属正常，想重建：

```powershell
New-Item -ItemType Junction `
  -Path "$env:USERPROFILE\.workbuddy\skills\life-decision-guide" `
  -Target "<本仓库路径>\.workbuddy\skills\life-decision-guide"
```

## 怎么用

问一件具体的事，别问抽象概念。三种典型问法：

```
每天通勤两小时值不值
朋友让我替他担保，签不签
被公司辞了，能领哪笔钱，先做什么
```

回答形态固定为：一句话结论 → 3~7 条按性价比排序的动作（每条带成本、收益、证据等级、
「第 N 节第 M 条（条目标题）」）→ 明确的「别做」清单 → 书里没写的部分如实标注。
数字一律照抄条目，不凭记忆补。

**查不到就说查不到**，这是这个 skill 最硬的一条：宁可说「书里没写」并标明下面的话是常识，
也不许编数字、编法条、编 DOI。

## 正文从哪来

按顺序找，命中即停：

1. 当前项目根或上级目录里同时有 `README.md` 和 `book/01-不要早死.md` → 直接读
2. `D:\workspace\git\HowToLiveBetter`（本机浅克隆副本，见 SKILL.md 第 1 步）
3. 都没有 → `git clone --depth 1` 到临时目录；网络不通就如实说取不到，**不凭记忆复述**
4. 只要单节时可直接 `curl` raw 文件，省一次 clone

节清单去读仓库根 `README.md` 的「这本书想回答的问题」表；性价比档的算法去读 `index.html` 的
`COST_W` 与 `e.ratio` 两行。**这两处会随上游变，本目录不抄。**

## 升级

上游 `skills/life-decision-guide/SKILL.md` 更新后，重跑一次「拷贝 + 打补丁」。补丁只有三处，
都写在文件里，`diff` 一眼能看出来：

```bash
UP=<本机 HowToLiveBetter 仓库>
DST=.workbuddy/skills/life-decision-guide/SKILL.md
cp "$UP/skills/life-decision-guide/SKILL.md" "$DST"
# 然后按 SKILL.md 里带「本机」字样的段落补回三处：
#   1) frontmatter 加 agent_created: true   —— 本仓库 CI 校验要求
#   2) 第 1 步「本机已有一份副本，优先用它」两行
#   3) 紧随其后的「目录不存在就走远程」兜底一行
diff -u "$UP/skills/life-decision-guide/SKILL.md" "$DST"   # 只应看到上面三处
```

校验：

```bash
python -m pytest tests/test_repo_layout.py -q     # frontmatter / name / 目录一致性
```

## 边界

- 给的是通用口径，**不替代医生、律师、会计**；具体病情、具体案件、具体税务只给方向和该找谁。
- 不给个性化投资建议。
- 与本仓库评分体系无关：**不参与四维评分、不写 `reviews.db`**，纯只读的知识检索。
- 书的观点是作者的，性价比分档也是作者划的；用户不同意时摆出书里的依据即可，不辩论。

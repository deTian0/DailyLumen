"""项目配置：路径、字段类型、个人化配置（可配置层）、评分阈值。

所有路径都相对「包目录」推导，因此无论项目放在何处都能正常工作。

本文件是**门面**（M16）：对外名字（``PROFILE`` / ``FEATURES`` / ``DB_PATH`` /
``CLICKUP_LISTS`` / ``FOOD_LIB`` …）全部保留；**凭据与环境差异**从
``settings.SETTINGS`` 派生，**个人参数与业务规则**仍写在本文件（入 git）。

小伙伴适配自己时改这些即可：

- ``PROFILE``      个人作息 / 目标 / 训练日约定（个人参数，⛔ 不进 ``.env``）
- ``PERSONAL_ITEMS`` 个人打卡项定义（补剂 / 护肤 / 自定义）——解析与归一化的单一来源
- ``HABITS``       行为习惯目录（ClickUp「习惯与打卡」）——与 PERSONAL_ITEMS **永不合并**
- ``LEARNING_TOPICS`` 学习主题目录（可选；未命中则 slugify）
- ``SPACED_REPEAT``   间隔重复天数（默认 1/3/7/16）
- ``SCORE_THRESHOLDS`` 四维评分阈值与权重（同时驱动「AI 评价与建议」的关注点规则）
- ``FEATURES``     功能开关：默认关闭你用不到的子命令（当前只有 ``new_day``）
- ``CLICKUP_LISTS`` 外部素材源（可选）：ClickUp list → 中文名 / 用途的一处定义
- ``CLICKUP_REVIEW_TASK`` 回写通道（可选）：「每日复盘总结」元任务的定位信息
- 凭据 / 路径覆盖 / 两源 API 端点与超时（练练 + ClickUp）→ 见 ``settings.py`` + 仓库根 ``.env``

改这几处即可，无需改动模板与其余代码。
"""
from __future__ import annotations

import os

from .settings import SETTINGS

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

# 包目录（本文件所在目录 = review_tool/）
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录（仓库根 = 每日复盘计划/）
BASE_DIR = os.path.dirname(PACKAGE_DIR)

# 数据库文件（可用 ``DAILYLUMEN_DB_PATH`` / ``.env`` 覆盖）
DB_PATH = SETTINGS.db_path

# 建表脚本
SCHEMA_PATH = os.path.join(PACKAGE_DIR, "schema.sql")

# 每日复盘 md 输入根目录（ingest 递归扫描，但跳过下面两个子目录）
INPUT_DIR = os.path.join(BASE_DIR, "每日复盘")

# 自动生成/回填的标准复盘目录（new-day / import-history 的输出根，按 YYYY-MM 归档）
GENERATED_DIR = os.path.join(INPUT_DIR, "复盘")

# 收件箱（用户投放原始简报/截图的目录，入库扫描时跳过）
INBOX_DIR = os.path.join(INPUT_DIR, "收件箱")

# 旧源文件归档目录（语雀原始格式，**不参与 ingest 扫描**）
ARCHIVE_SRC_DIR = os.path.join(INPUT_DIR, "历史源复盘")

# 复盘模板
TEMPLATE_PATH = os.path.join(BASE_DIR, "每日复盘模板.md")

# 历史语雀文件来源目录（``DAILYLUMEN_HISTORY_SRC`` / ``.env``；不内置个人路径）
HISTORY_SRC_DIR = SETTINGS.history_src_dir

# 练练健身（KeepStrong）环境默认 —— 密钥只从 SETTINGS / .env 读，绝不写在这里
KS_DEFAULTS = {
    "base_url": SETTINGS.keepstrong_base_url,
    "skill_version": SETTINGS.keepstrong_skill_version,
    "agent_name": SETTINGS.keepstrong_agent_name,
    "timeout_s": SETTINGS.keepstrong_timeout_s,
    "cache_dir": SETTINGS.keepstrong_cache_dir,
}

# 练练动作名 / actionId → item_key（M18）。未命中则走 TRAINING_MOVES，再 slugify。
# 例：{"act_0ef8…": "goblet_squat", "壶铃深蹲": "goblet_squat"}
KS_ACTION_MAP: dict[str, str] = {}

# ---------------------------------------------------------------------------
# 字段类型（解析时按此转换）
# ---------------------------------------------------------------------------

DIMENSIONS = ["health_score", "work_score", "learn_score", "life_score"]

INT_FIELDS = {
    "sleep_quality", "exercise_min", "diet_kcal", "meals_count",
    "carbs_g", "fat_g", "protein_g",
    "health_score", "work_score", "learn_score", "life_score",
}
FLOAT_FIELDS = {"sleep_h", "phone_h", "deepwork_h", "learn_h", "life_h"}
BOOL_FIELDS = {"training_day", "commute_done", "breakfast_on_time"}
# ⚠️ ``commute_done`` 自 v1.37.0 起**废弃**（用户 2026-10-21 拍板）：
# 通勤固定 2×2.4km/日，「今天通勤了吗」恒为是，79 天填了 18 天（22.8%），
# 这个数字反映的是「懒得填」而不是通勤异常。模板已删该行、报告已不出该项；
# 列与解析**保留**（老 md 仍能入库、不做破坏性迁移），但不再有任何读者。
TEXT_FIELDS = {"weekday", "energy", "mood", "summary"}

# 星期中文（0=周一），new-day 与历史导入共用
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]

# ---------------------------------------------------------------------------
# ClickUp list ID —— **单一事实源**（v1.25.0 收口）
#
# ⛔ 不要在别处再写字面量：``CLICKUP_LISTS`` / ``HABITS_LIST_ID`` /
# ``LEARNING_LIST_IDS`` / ``CLICKUP_REVIEW_TASK`` 全部引用这里。
# 换 list / 改名 / 删 list 只改这一处 —— 此前 ``901422213139`` 在同一文件里
# 出现 4 次，改一次要改四处，漏一处就静默指向错 list。
# ---------------------------------------------------------------------------

LIST_DAILY = "901422213138"       # 日常事务（行为流水 + 学习进度 + 读书进度）
LIST_HABITS = "901422213139"      # 习惯与打卡
LIST_WORK = "901410092299"        # 工作（工时 / 工单记录）
LIST_INCUBATOR = "901422213132"   # 项目孵化
LIST_ANNUAL = "901422213133"      # 2026 年度目标

# 时区口径**单一来源**：东八区。ClickUp 时间戳按小时算、练练 API 的
# ``X-Timezone-Offset`` 按分钟算 —— 量纲各自换算，事实只此一处。
TZ_OFFSET_HOURS = 8

# ClickUp 归属口径（v1.37.1 修正）：
#
# 这张团队工时表是用本人账号建的，**所有条目（不管姓名前缀是谁）实际执行人
# 都是本人** —— 姓名位是「任务下发人」，不是执行人。2026-10-21 曾按姓名位
# 排除同事前缀（``CLICKUP_TEAMMATES``），实测把 8-20 之后几乎全部工作流水
# 都排除了（那些都是同事下发、本人执行的活）。v1.37.1 起该口径废除：
# ``is_self`` 恒为 True，``owner`` 字段语义 = 下发人。
# 历史名单（从 692 条任务姓名位实测）：李扬/常哲/李苏/石朋/向磊/王璐瑶/
# 刘同勇/王博/徐迹/杨杨/侯玖成/唐奉/霍运川/吕振远 —— 存档于此注释，不再参与判定。

# ---------------------------------------------------------------------------
# 功能开关（可配置层）
#
# 关掉某项后，对应子命令**仍然存在**（仍在 `-h` 里、仍可显式调用），但会拒绝
# 执行并告诉你去哪打开。目的是防止「AI / 脚本误调用一个你并不用的功能」——
# 静默跑通比直接拒绝更危险（例如误生成一份空模板，你却发现不了）。
#
# · 改回 True 即启用；CLI 的 ``-h`` 不受开关影响（帮助永远可读）。
# · 开关只作用于**命令入口**（各模块的 ``main``），模块内的纯函数
#   （如 ``new_day.generate``）不拦 —— 测试与调用方仍可直接复用。
# ---------------------------------------------------------------------------

FEATURES = {
    # new-day：按模板生成当天复盘文件（写入 ``每日复盘/复盘/YYYY-MM/``）。
    # 默认关闭：手动复制模板更顺手，且手动复制只需改「日期」「星期」两处。
    "new_day": False,
}

# ---------------------------------------------------------------------------
# 个人化配置
# ---------------------------------------------------------------------------

PROFILE = {
    "name": "63516",
    # 早餐作息窗口（仅用于模板展示与文档说明）
    "breakfast_window": "08:00-09:00",
    # 三大营养素每日目标（g）：供「AI 评价与建议」判定摄入是否达标，留空则不检查。
    # 默认值 = 当前用户薄荷健康 App 的目标基线（2026-10-16 用户确认维持不变）。
    "macro_targets": {"carbs_g": 220, "protein_g": 82, "fat_g": 46},
    # 训练日约定：0=周一 … 6=周日。
    # ⚠️ **2026-10-16 起降级为「离线兜底」** —— 训练日改为**动态**，以练练健身 App
    # 为准（见 docs/生活管家路线图.md M20）：取被复盘日（= 执行日的「昨日」）
    # 的**已完成**训练记录判定。本字段仅在练练取不到数据（无 Key / 断网）时由
    # ingest.fill_training_day 兜底，避免「缺失」的天数静默从 WHERE training_day=1
    # 的过滤中消失。⛔ 不再作为训练日的主判据。
    "training_weekdays": [0, 1, 2, 4, 5],
    # 身高 (cm)：供 BMI 渲染；未配置时 body 报告显示「未配置身高」，不报错（M9）。
    "height_cm": 170,
}

# ---------------------------------------------------------------------------
# 常吃食物库（M12 · 建议侧静态配置，不做记录表）
#
# 每项宏量相对 ``per``（默认 100）：建议克数 = amount，贡献 = 宏量 × (amount/per)。
# 可数单位（个 / 份）时 ``per`` 通常为 1。aliases 仅供人读 / 未来解析，报告按 key 引用。
# ---------------------------------------------------------------------------

FOOD_LIB = [
    # —— 蛋白主源 ——
    {
        "key": "chicken_breast", "name": "鸡胸肉", "unit": "g", "per": 100,
        "kcal": 133, "carbs": 0, "protein": 23.1, "fat": 5,
        "aliases": ["鸡胸", "鸡胸肉"],
    },
    {
        "key": "egg", "name": "鸡蛋", "unit": "个", "per": 1,
        "kcal": 72, "carbs": 0.4, "protein": 6.3, "fat": 5,
        "aliases": ["鸡蛋", "蛋"],
    },
    {
        "key": "milk", "name": "牛奶", "unit": "ml", "per": 100,
        "kcal": 54, "carbs": 5, "protein": 3.2, "fat": 3.2,
        "aliases": ["牛奶", "全脂牛奶"],
    },
    {
        "key": "greek_yogurt", "name": "希腊酸奶", "unit": "g", "per": 100,
        "kcal": 97, "carbs": 3.6, "protein": 9, "fat": 5,
        "aliases": ["希腊酸奶", "酸奶"],
    },
    {
        "key": "tofu", "name": "北豆腐", "unit": "g", "per": 100,
        "kcal": 76, "carbs": 1.9, "protein": 8.1, "fat": 4.8,
        "aliases": ["豆腐", "北豆腐"],
    },
    {
        "key": "shrimp", "name": "虾仁", "unit": "g", "per": 100,
        "kcal": 93, "carbs": 0.2, "protein": 18.6, "fat": 1.4,
        "aliases": ["虾仁", "虾"],
    },
    {
        "key": "lean_beef", "name": "瘦牛肉", "unit": "g", "per": 100,
        "kcal": 125, "carbs": 0, "protein": 20.2, "fat": 4.4,
        "aliases": ["瘦牛肉", "牛肉"],
    },
    {
        "key": "salmon", "name": "三文鱼", "unit": "g", "per": 100,
        "kcal": 208, "carbs": 0, "protein": 20, "fat": 13,
        "aliases": ["三文鱼", "鲑鱼"],
    },
    {
        "key": "whey", "name": "乳清蛋白粉", "unit": "g", "per": 30,
        "kcal": 120, "carbs": 2, "protein": 24, "fat": 1.5,
        "aliases": ["蛋白粉", "乳清", "whey"],
    },
    {
        "key": "cottage_cheese", "name": "低脂奶酪", "unit": "g", "per": 100,
        "kcal": 98, "carbs": 3.4, "protein": 11, "fat": 4.3,
        "aliases": ["低脂奶酪", "cottage cheese"],
    },
    # —— 碳水主源 ——
    {
        "key": "rice", "name": "米饭", "unit": "g", "per": 100,
        "kcal": 116, "carbs": 26, "protein": 2.6, "fat": 0.3,
        "aliases": ["米饭", "白米饭", "米饭（熟）"],
    },
    {
        "key": "oats", "name": "燕麦片", "unit": "g", "per": 100,
        "kcal": 367, "carbs": 66, "protein": 13, "fat": 7,
        "aliases": ["燕麦", "燕麦片"],
    },
    {
        "key": "whole_bread", "name": "全麦面包", "unit": "g", "per": 100,
        "kcal": 247, "carbs": 41, "protein": 13, "fat": 4.2,
        "aliases": ["全麦面包", "全麦吐司"],
    },
    {
        "key": "sweet_potato", "name": "红薯", "unit": "g", "per": 100,
        "kcal": 99, "carbs": 24, "protein": 1.6, "fat": 0.2,
        "aliases": ["红薯", "地瓜"],
    },
    {
        "key": "potato", "name": "土豆", "unit": "g", "per": 100,
        "kcal": 77, "carbs": 17, "protein": 2, "fat": 0.1,
        "aliases": ["土豆", "马铃薯"],
    },
    {
        "key": "pasta", "name": "意面", "unit": "g", "per": 100,
        "kcal": 131, "carbs": 25, "protein": 5, "fat": 1.1,
        "aliases": ["意面", "意大利面", "意面（熟）"],
    },
    {
        "key": "banana", "name": "香蕉", "unit": "个", "per": 1,
        "kcal": 107, "carbs": 27, "protein": 1.3, "fat": 0.4,
        "aliases": ["香蕉"],
    },
    {
        "key": "apple", "name": "苹果", "unit": "个", "per": 1,
        "kcal": 104, "carbs": 28, "protein": 0.5, "fat": 0.3,
        "aliases": ["苹果"],
    },
    # —— 蔬果 / 脂肪 ——
    {
        "key": "broccoli", "name": "西兰花", "unit": "g", "per": 100,
        "kcal": 34, "carbs": 7, "protein": 2.8, "fat": 0.4,
        "aliases": ["西兰花", "花椰菜"],
    },
    {
        "key": "spinach", "name": "菠菜", "unit": "g", "per": 100,
        "kcal": 23, "carbs": 3.6, "protein": 2.9, "fat": 0.4,
        "aliases": ["菠菜"],
    },
    {
        "key": "cucumber", "name": "黄瓜", "unit": "g", "per": 100,
        "kcal": 15, "carbs": 3.6, "protein": 0.7, "fat": 0.1,
        "aliases": ["黄瓜"],
    },
    {
        "key": "avocado", "name": "牛油果", "unit": "g", "per": 100,
        "kcal": 160, "carbs": 8.5, "protein": 2, "fat": 15,
        "aliases": ["牛油果", "鳄梨"],
    },
    {
        "key": "peanut", "name": "花生", "unit": "g", "per": 100,
        "kcal": 567, "carbs": 16, "protein": 26, "fat": 49,
        "aliases": ["花生", "花生米"],
    },
    {
        "key": "walnut", "name": "核桃", "unit": "g", "per": 100,
        "kcal": 654, "carbs": 14, "protein": 15, "fat": 65,
        "aliases": ["核桃"],
    },
    {
        "key": "olive_oil", "name": "橄榄油", "unit": "g", "per": 10,
        "kcal": 90, "carbs": 0, "protein": 0, "fat": 10,
        "aliases": ["橄榄油"],
    },
    {
        "key": "soy_milk", "name": "原味豆浆", "unit": "ml", "per": 100,
        "kcal": 31, "carbs": 1.2, "protein": 3, "fat": 1.6,
        "aliases": ["豆浆", "原味豆浆"],
    },
]

# 营养报告规则（阈值是配置，不进表 —— G4）
NUTRITION_RULES = {
    "extreme_kcal": 1000,       # 连续低于此热量 → 强提示
    "extreme_streak_days": 3,   # 连续天数门槛
    "max_suggest_foods": 3,     # 贪心组合上限
    "expected_meals": 3,        # 三餐结构预期餐次
}

# 体征目标带（配置不是数据，不进表 —— G4）。未配置时报告显示「未配置」。
# 2026-10-16 用户给定：目标体重 **65 kg**（起点 82.1 kg，减重方向）→ 设为
# 65 ± 1 kg 的**达标带**。「距目标 / 预计达标周数」按最近端推算（core/body.py 口径）。
BODY_TARGETS = {
    "weight_kg_low": 64.0,
    "weight_kg_high": 66.0,
}

# 体征字段登记（侧车 → body_metrics）。⛔ 禁止并入 FLOAT_FIELDS / daily_reviews COLUMNS。
BODY_FLOAT_FIELDS = {"weight_kg", "body_fat_pct", "waist_cm"}
BODY_TEXT_FIELDS = {"src", "note"}
# md 数据块字段名 → body_metrics 列名
BODY_FIELD_MAP = {
    "weight_kg": "weight_kg", "体重_kg": "weight_kg", "体重": "weight_kg",
    "body_fat_pct": "body_fat_pct", "体脂率": "body_fat_pct", "体脂": "body_fat_pct",
    "waist_cm": "waist_cm", "腰围_cm": "waist_cm", "腰围": "waist_cm",
    "body_src": "src", "体征来源": "src",
    "body_note": "note", "体征备注": "note",
}

# 打卡时段（模板里的小节标题 -> 时段 key）
SLOT_CN = {"morning": "晨间", "noon": "午间", "evening": "晚间"}
SLOT_BY_CN = {v: k for k, v in SLOT_CN.items()}


# ---------------------------------------------------------------------------
# 个人打卡项定义（单一来源）
#
# 每条 = 一个「规范项」：
#   category  归属类别（服药 / 护肤 / 自定义…），落在 personal_tracks.category
#   key       规范 ID（不含时段），落在 personal_tracks.item_key
#   per_slot  是否「按时段区分」
#               True  -> 时段由模板小节标题（**晨间（起床后）**）决定，
#                        标题缺失时记为「时段未知」（如 Move Free 午/晚都可能吃）
#               False -> 时段固定为 slot（可为 None = 不分时段，如护肤）
#   slot      默认 / 固定时段（morning / noon / evening / None）
#   label     展示名，落在 personal_tracks.item
#   aliases   模板文本里可能出现写法的关键词，命中任一即归一到本项
#
# 归一化的意义：让「依从率」可以按 item_key 稳定聚合，不再受手写文本差异影响。
# ---------------------------------------------------------------------------

PERSONAL_ITEMS = [
    {
        "category": "服药", "key": "coq10", "per_slot": False, "slot": "morning",
        "label": "CoQ10 ×1", "aliases": ["CoQ10", "辅酶Q10"],
    },
    {
        "category": "服药", "key": "exia_am", "per_slot": False, "slot": "morning",
        "label": "Exia 早3", "aliases": ["Exia 早3", "Exia早3", "Exia 早"],
    },
    {
        "category": "服药", "key": "vitb", "per_slot": False, "slot": "noon",
        "label": "复合维生素B族 ×1", "aliases": ["复合维生素B族", "维生素B族"],
    },
    {
        "category": "服药", "key": "exia_pm", "per_slot": False, "slot": "evening",
        "label": "Exia 晚3", "aliases": ["Exia 晚3", "Exia晚3", "Exia 晚"],
    },
    {
        # Move Free 午 / 晚都可能吃：按时段区分，标题缺失则记「时段未知」
        "category": "服药", "key": "movefree", "per_slot": True, "slot": None,
        "label": "Move Free 红色 ×1", "aliases": ["Move Free", "MoveFree", "move free"],
    },
    {
        # 护肤不分时段：无论出现在哪个小节都不带时段后缀
        "category": "护肤", "key": "skincare", "per_slot": False, "slot": None,
        "label": "护肤", "aliases": ["护肤"],
    },
]

# 打卡行里出现这些词，才按「补剂」处理（去掉「补剂：」前缀后再拆项）
SUPPLEMENT_MARKER = "补剂"


# ---------------------------------------------------------------------------
# 行为习惯（ClickUp「习惯与打卡」list 901422213139）
#
# 与 PERSONAL_ITEMS（补剂 / 护肤）是**两套体系**（R3）：
#   · 本表 aliases 不得与 PERSONAL_ITEMS aliases 冲突（tests/test_config.py 守卫）
#   · 落库进 habit_logs，绝不进 personal_tracks；不参与四维评分（G5）
#   · 权威：ClickUp 执行层 → habit_logs 快照（唯一 ClickUp→库写方向）
#
#   key              规范 ID（habit_logs.habit_key）
#   label            展示名
#   aliases          ClickUp 任务名可能写法（最长优先匹配）
#   target_per_week  周目标完成次数（报告用）
#   alert_days       连续未完成达到此天数 → doctor 断更提示（建议性）
# ---------------------------------------------------------------------------

HABITS = [
    {
        "key": "reading_30",
        "label": "每日阅读 30 分钟",
        "aliases": ["每日阅读 30 分钟", "每日阅读30分钟", "每日阅读"],
        "target_per_week": 7,
        "alert_days": 3,
    },
    {
        "key": "lianlian",
        "label": "练练健身",
        "aliases": ["练练健身", "练练"],
        "target_per_week": 5,
        "alert_days": 3,
    },
    {
        "key": "notes_app",
        "label": "整理随手记 app 数据",
        "aliases": ["整理随手记app数据", "整理随手记 app 数据", "整理随手记"],
        "target_per_week": 7,
        "alert_days": 5,
    },
    {
        "key": "daily_review",
        "label": "每日复盘总结",
        "aliases": ["每日复盘总结", "每日复盘"],
        "target_per_week": 7,
        "alert_days": 2,
    },
    {
        "key": "maimemo",
        "label": "墨墨背单词",
        "aliases": ["墨墨背单词app", "墨墨背单词 app", "墨墨背单词", "墨墨"],
        "target_per_week": 7,
        "alert_days": 3,
    },
    {
        "key": "good_habit",
        "label": "寻找并调整好习惯",
        "aliases": [
            "寻找一些个人提升的好习惯，然后调整自己",
            "寻找并调整好习惯",
            "寻找一些个人提升的好习惯",
        ],
        "target_per_week": 3,
        "alert_days": 7,
    },
]

# ClickUp「习惯与打卡」list id（select_habits / habit_sync 默认源）
HABITS_LIST_ID = LIST_HABITS


# ---------------------------------------------------------------------------
# 学习主题目录（可选）+ 间隔重复
#
# LEARNING_TOPICS：未命中时 core/learning 用 slugify(主题) 作 topic_key，
# 保证 md → 库可重建。别名最长优先（与 HABITS / PERSONAL_ITEMS 同口径）。
# SPACED_REPEAT.intervals：学习次数 n → stage = min(n-1, len-1)，
# due = last_seen + intervals[stage]。review_queue 必须可从 learning_logs 重建。
# ---------------------------------------------------------------------------

LEARNING_TOPICS = [
    {
        "key": "python",
        "label": "Python",
        "aliases": ["Python", "python", "Py"],
    },
    {
        "key": "system_design",
        "label": "系统设计",
        "aliases": ["系统设计", "System Design", "架构"],
    },
    {
        "key": "english",
        "label": "英语",
        "aliases": ["英语", "English", "英文"],
    },
    {
        "key": "reading",
        "label": "阅读",
        "aliases": ["阅读", "读书", "Reading"],
    },
    {
        "key": "growth_course",
        "label": "成长课",
        "aliases": ["成长课", "14周计划", "成长课 · 14周计划"],
    },
]

# 简化 SM-2：1d / 3d / 7d / 16d
SPACED_REPEAT = {
    "intervals": [1, 3, 7, 16],
}

# 学习证据链 ClickUp list；素材用 clickup --list 组合即可。
# v1.24.0：「成长课 · 14周计划」与「阅读与学习」两个 list 已整体并入「日常事务」
# （原 901422213140 / 901422213142 已删除），课程与读书完成记录随日常事务日采。
LEARNING_LIST_IDS = (LIST_DAILY,)


# ---------------------------------------------------------------------------
# 承诺对账（v10 / M29）
#
# 「三、一个改进点」「四、明日 Top 3」里写的东西，此前代码一次都没读过
# （`core/bodyweight.py:28` 明确注释「那是计划/意愿」）。本表把承诺落库并对账。
#
# ⛔ 设计红线：**只做证据型判定，不做语义猜测**。
#   - 判据必须来自次日已入库的结构化字段（learn_h / exercise_min / fat_g /
#     bedtime / personal_tracks …），可复现、可单测；
#   - 映射不到字段的承诺老实标 `unmapped`，**不猜、不当成未兑现**；
#   - 兑现率只在「可判定」子集上算，分子分母都暴露给用户；
#   - **不进四维评分、不加惩罚** —— 它是镜子，不是鞭子。
#
# 桶顺序即匹配优先级：越具体的桶越靠前（补剂 > 运动 > 学习 > 饮食 > 睡眠 > 手机），
# 同桶内关键词按长度降序（「手机离手」优先于「手机」）。
# ---------------------------------------------------------------------------
PROMISE_BUCKETS = [
    {
        "key": "supplement",
        "label": "补剂",
        # 判据：次日 personal_tracks 里对应 item done=1（二元，最硬）
        "field": "personal_tracks",
        "keywords": ["CoQ10", "coq10", "Move Free", "Exia", "维生素B", "维B",
                     "补剂", "鱼油", "钙片"],
    },
    {
        "key": "exercise",
        "label": "运动",
        # 判据：次日 exercise_min > 0（有约束时取约束分钟数）
        "field": "exercise_min",
        "keywords": ["练练", "健身", "训练", "跑步", "运动", "锻炼", "拉伸",
                     "俯卧撑", "深蹲", "通勤骑行"],
    },
    {
        "key": "learn",
        "label": "学习",
        # 判据：次日 learn_h*60 >= 约束分钟（无约束则 > 0）
        "field": "learn_h",
        "keywords": ["积极心理学", "微信读书", "背单词", "墨墨", "成长课", "听课",
                     "看课", "读书", "阅读", "第0", "第1", "讲", "章节", "学习"],
    },
    {
        "key": "diet",
        "label": "饮食",
        # 判据：有阈值（如脂肪 ≤70g）时比对次日宏量；无阈值 → unmapped
        "field": "fat_g",
        "keywords": ["脂肪", "热量", "kcal", "大卡", "碳水", "蛋白质",
                     "肥肠", "主菜", "外卖", "加餐", "饮食", "午餐", "晚餐", "早餐"],
    },
    {
        "key": "sleep",
        "label": "睡眠",
        # 判据：次日 bedtime <= 约束时刻（如「23:30 前」），否则 unmapped
        "field": "bedtime",
        "keywords": ["入睡", "睡觉", "早睡", "手机离手", "放下手机", "躺下",
                     "手机放客厅", "关灯", "熄灯", "上床", "洗漱"],
    },
    {
        "key": "phone",
        "label": "手机",
        # 判据：次日 phone_h < 前 7 日均值（弱证据 → partial，不算兑现）
        "field": "phone_h",
        "keywords": ["手机", "屏幕", "刷视频", "短视频", "番茄小说", "王者荣耀",
                     "玩游戏", "打游戏"],
    },
    {
        "key": "work",
        "label": "工作",
        # 判据：次日 deepwork_h > 0（有约束时取约束小时/分钟）
        "field": "deepwork_h",
        "keywords": ["深度工作", "禅道", "加班", "工时", "日报", "周报",
                     "代码", "合并", "重构", "部署", "接口", "需求", "工作"],
    },
]

PROMISE_KINDS = {
    "improvement": {"label": "改进点", "heading": "改进点"},
    "plan": {"label": "明日 Top 3", "heading": "明日"},
}

# 模板残留：9 月版模板把**填写提示**写成了列表项（`- 通常落在：…`），
# 用户在「一个改进点」下留空时，这行提示就成了唯一内容 —— 它不是承诺。
# 实测：三条提示语分别占了 42 / 42 / 26 天。现模板已改成 `>` 引用块
# （解析器天然跳过），这份名单只兜存量。
# ⛔ 必须**归一化后全等**比对，不做模糊匹配，避免误伤真实条目。
PROMISE_PROMPT_LINES = [
    "通常落在：睡太晚 / 屏幕太久 / 一件一直拖着的事 / 某次情绪消耗。",
    "如果今天只改一件事让明天更好，改什么？写不出就空着。",
    "明天最想推进的三件事，写就行，不强求完成。",
    "只写一个，越具体越好（动作 + 时间）。",
    "给重要的事配一个时间锚点（如「19:30 提醒 Keep」），更容易落地。",
]

# 放弃标记：写了但等于没写。全等匹配（「无糖」不会中招）。
# 「忘记了 / 想不到」是 meta 陈述，不是承诺 —— 计入「写了空」而非「未兑现」。
PROMISE_EMPTY_MARKERS = [
    "空", "（空）", "(空)", "无", "没有", "（未填写）", "(未填写)", "未填写",
    "忘记了", "忘了", "想不到", "不记得了", "记不得了", "想不出",
]

# 显式放弃（v1.37.0 / D1，2026-10-21 用户拍板）
#
# 与上面的 EMPTY_MARKERS 的差别是**语义方向**，不是措辞：
#   - 空 / 忘记了 / 想不到 → **无声空转**。用户没做决定，系统只能当没写。
#   - 今天不设            → **显式决定**。用户决定了今天不设，这是有效信息。
# 实测：10 月 30 天里 25 天「改进点」是 `- ` 或 `1. 空`，全是前者。
# 让「今天不设」可写，是把无声空转变成可统计的选择 —— 不设的天数本身有意义
# （连续多天不设，说明这个仪式对当前生活没抓手）。
#
# 全等匹配（归一化后），「不设上限」不会中招。入库时 bucket 记为
# ``PROMISE_DECLINED_BUCKET``，对账状态记 ``declined``，**不进兑现率分母**。
PROMISE_DECLINED_MARKERS = [
    "今天不设", "今日不设", "今天不设改进点", "本次不设", "不设", "跳过",
    "今天跳过", "今天没有改进点", "无改进点",
]
PROMISE_DECLINED_BUCKET = "declined"


# ---------------------------------------------------------------------------
# 徒手训练折算（描述文本 -> 运动时长）
#
# 用途：你在「二、今日三件事」里写了「做了二十个俯卧撑」，但「运动时长_min」
# 字段留空 —— 于是该字段为 NULL，训练日达标率统计直接失效（运动占健康分
# 权重 0.25，是全部健康子项里最重的一项）。本表让描述里的动作自动进入
# 运动时长，规则是**确定性**的（同样的文本永远得到同样的分钟数）。
#
# 折算模型
#   净执行时间 = 次数 / per_minute            （1 次 ≈ 60/per_minute 秒）
#   组间休息   = (组数 - 1) × set_rest_sec
#   单日结果   = clamp(Σ(净执行 + 组间休息), min_session_min, max_session_min)
#
# 为什么下限是 10：健康分对**空值子项是整项剔除**（按剩余权重归一），
# 所以「如实记录一个很小的量」反而比「留空」更吃亏 —— 分母变大、均值被拉低。
# 取下限 10（= 训练日「尚可」阈值）保证「如实记录」不会倒扣，同时它本身也
# 站得住：一次徒手训练课的最低有效时长就是十来分钟。
#
# 扩展：按同样结构追加动作即可（键名用中文动作名，aliases 放各种写法）。
# ---------------------------------------------------------------------------

BODYWEIGHT_MOVES = {
    "俯卧撑": {
        "aliases": ["俯卧撑", "掌上压", "push-up", "pushup", "push up"],
        "per_minute": 20,     # 净速率：1 次 / 3 秒
        "set_rest_sec": 60,   # 组间休息 60 秒
        "default_reps": 20,   # 只提到动作、没写数量时：按 1 组 × 20 次估
    },
    "深蹲": {
        "aliases": ["深蹲", "徒手深蹲", "自重深蹲", "squat"],
        "per_minute": 15,
        "set_rest_sec": 60,
        "default_reps": 15,
    },
    "卷腹": {
        "aliases": ["卷腹", "仰卧起坐", "crunch"],
        "per_minute": 25,
        "set_rest_sec": 45,
        "default_reps": 20,
    },
    "平板支撑": {
        "aliases": ["平板支撑", "平板", "plank"],
        "per_minute": 1,      # 按秒计时为主；次数折算兜底
        "set_rest_sec": 30,
        "default_reps": 60,
    },
    "波比跳": {
        "aliases": ["波比跳", "波比", "burpee", "burpees"],
        "per_minute": 10,
        "set_rest_sec": 60,
        "default_reps": 10,
    },
}

BODYWEIGHT_RULES = {
    "min_session_min": 10,  # 单日下限（= 训练日「尚可」阈值，防止如实记录反倒扣分）
    "max_session_min": 45,  # 单日上限（防离谱外推）
    "max_reps": 1000,       # 单日次数合理性上限，超出视为误写并回退到 default_reps
}


# ---------------------------------------------------------------------------
# 训练动作目录 / 课表 / 教练规则（M10）
#
# TRAINING_MOVES = 动作目录（结构 / 部位 / 可选折算参数）
# BODYWEIGHT_MOVES = 徒手折算参数（「三件事」描述 → 分钟）
# 约束：BODYWEIGHT_MOVES 的每个 key 必须在 TRAINING_MOVES 里；两者 alias 不得互抢。
# ---------------------------------------------------------------------------

TRAINING_MOVES = {
    "俯卧撑": {
        "aliases": ["俯卧撑", "掌上压", "push-up", "pushup", "push up"],
        "body_part": "胸",
        "per_minute": 20,
        "set_rest_sec": 60,
        "default_reps": 20,
    },
    "深蹲": {
        "aliases": ["深蹲", "徒手深蹲", "自重深蹲", "squat"],
        "body_part": "腿",
        "per_minute": 15,
        "set_rest_sec": 60,
        "default_reps": 15,
    },
    "卷腹": {
        "aliases": ["卷腹", "仰卧起坐", "crunch"],
        "body_part": "核心",
        "per_minute": 25,
        "set_rest_sec": 45,
        "default_reps": 20,
    },
    "平板支撑": {
        "aliases": ["平板支撑", "平板", "plank"],
        "body_part": "核心",
        "per_minute": 1,
        "set_rest_sec": 30,
        "default_reps": 60,
    },
    "波比跳": {
        "aliases": ["波比跳", "波比", "burpee", "burpees"],
        "body_part": "全身",
        "per_minute": 10,
        "set_rest_sec": 60,
        "default_reps": 10,
    },
    "卧推": {
        "aliases": ["卧推", "杠铃卧推", "哑铃卧推", "bench"],
        "body_part": "胸",
        "default_set_min": 2.5,
    },
    "划船": {
        "aliases": ["划船", "杠铃划船", "哑铃划船", "row"],
        "body_part": "背",
        "default_set_min": 2.5,
    },
    "硬拉": {
        "aliases": ["硬拉", "罗马尼亚硬拉", "deadlift"],
        "body_part": "腿",
        "default_set_min": 3.0,
    },
    "肩推": {
        "aliases": ["肩推", "推举", "哑铃肩推", "overhead press"],
        "body_part": "肩",
        "default_set_min": 2.0,
    },
    "跑步": {
        "aliases": ["跑步", "慢跑", "有氧跑", "run", "running"],
        "body_part": "有氧",
    },
    "引体向上": {
        "aliases": ["引体向上", "引体", "pull-up", "pullup"],
        "body_part": "背",
        "per_minute": 8,
        "set_rest_sec": 90,
        "default_reps": 5,
    },
}

# 可选课表：weekday(0=周一) → 计划名。空 dict = 用 training_weekdays 计数作计划课次。
TRAINING_PLAN: dict[int, str] = {}

COACH_RULES = {
    "min_ratio": 0.8,              # 完成课次 / 计划课次 ≥ 此值才建议加量
    "max_consecutive_days": 3,     # 连续训练天数上限，达线强制建议恢复
    "progression_cv": 0.10,        # 近 N 次体积变异系数 ≤ 此值视为「稳定」
    "add_sets": 1,
    "add_reps": 2,
    "body_part_gap_hours": 48,     # 同一部位主项最短间隔
    "progression_lookback": 3,     # 渐进看近几次
}


# ---------------------------------------------------------------------------
# 评分阈值（可配置层）：默认值为当前用户的评分偏好。
# score.py 引用这些常量计算四维分；「AI 评价与建议」的文案也从这里派生，
# 因此改这里不会出现「阈值改了、文案还在说老数字」的问题。
# ---------------------------------------------------------------------------

# 评分标尺 v2（v1.34.0 重设：阈值分档 → 锚点插值）
#
# 为什么重设：v1 的标尺是照着「不存在的人」定的 —— 它同时要求 6h 深度工作、
# 3h 学习、3h 生活、8h 睡眠、30min 训练、≤4h 屏幕，加起来一天有 40 小时。
# 后果有三条，全部有实测数据支撑（78 天 / 2026-07-16~10-20）：
#   1. 时长维分值集合只有 {1,2,3,4,5,7,9}，**6 分不可达** —— 于是「及格 6」
#      实为「必须踩 good 档」；学习维全库仅 3/63 天达到 2h 线。
#   2. 健康维三个子项出现「一个分值覆盖 >50% 样本」的死档：入睡 89% 同分（3）、
#      屏幕 74% 同分（2）、运动 69% 同分（2）—— 三者合计 0.55 权重，把健康分
#      钉在 4.67、上限 7；系统分随之常年挤在 3.8~5.7，趋势扁平。
#   3. 「6h 深度工作」那天往往学习 / 生活都是 0 —— 标尺却给单项满分、
#      再用算术平均把总分抬高，等于给「牺牲两维换一维」发及格分。
#
# 三条设计判据（改数字前请先读，改完必须重算 + 回写文档）：
#   1. **满分 = 帕累托点，不是单项极限**。24h 刚性支出（睡 7.5 + 通勤 1 +
#      三餐洗漱 2.5 + 工作 8）后只剩约 5h 自主时间，四维都从这个池子里抢。
#      所以满分档要「可达但稀少」（实测命中率 5~15%），不是人人天天拿。
#   2. **任何单个分值不得覆盖 >50% 的样本** —— 超了就是死档，该维度失去分辨率。
#   3. **1~10 每个整数都要可达且随原始值单调** —— 所以用锚点插值，不用分档
#      （分档必然产生空档，v1 的 6 分不可达就是这么来的）。
#
# ⛔ 改这里的数字 = 改历史分数口径：必须 `recompute-scores --apply && sync-docs`，
#    并回填周报 / 月报（它们不在 sync-docs 覆盖范围内）。

# 饮食目标热量（kcal）：从 PROFILE["macro_targets"] 推导（碳水/蛋白 4 kcal/g，
# 脂肪 9 kcal/g）。改宏量目标 → 饮食分的中心自动跟着走，不用两处维护。
# 宏量目标缺失时退回 None，由 compute 侧用 fallback_target 兜底。
_MACROS = PROFILE.get("macro_targets") or {}
DIET_TARGET_KCAL = (
    float(_MACROS.get("carbs_g", 0)) * 4
    + float(_MACROS.get("protein_g", 0)) * 4
    + float(_MACROS.get("fat_g", 0)) * 9
) or None

SCORE_THRESHOLDS = {
    # ===== 时长三维：锚点插值 =====
    # 每项 = [(小时, 分值), ...]，区间内线性插值，两端封顶。
    # 锚点语义统一：5 = 及格（可持续的日常水平）/ 7 = 好 / 10 = 理想（罕见但真实发生）。
    #
    # work（8h 工作制里能挤出的「有效深度时间」，不是加班时长）：
    #   2h 及格=正常一天的产出｜4h 好=无会议的高效日｜7h 理想=全库 1 天。
    "work": {"anchors": [(0, 1), (0.5, 2), (1, 3), (1.5, 4), (2, 5),
                         (3, 6), (4, 7), (5, 8), (6, 9), (7, 10)]},
    # learn：0.5h = 有学但蜻蜓点水｜1h 及格 = 可持续的每日投入｜
    #   2h 好｜3h 理想（全库 1 天）。
    "learn": {"anchors": [(0, 1), (0.5, 4), (1, 6), (1.5, 7), (2, 8), (3, 10)]},
    # life：1h 及格｜2h 好｜4h 理想（周末实测 7 天到顶格）。
    "life": {"anchors": [(0, 1), (0.25, 2), (0.5, 3), (0.75, 4), (1, 5),
                         (1.5, 6), (2, 7), (3, 9), (4, 10)]},

    # ===== 健康六子项：阈值分档（都是单指标，分档比插值更易解释）=====
    # 每项 = [[阈值, 分值], ...] + floor（超出最后一档时取 floor）。
    # gte=True 表示「越大越好」（阈值是下界）；False 表示「越小越好」（上界）。
    #
    # 睡眠时长(h)：8h 理想 / 7.5 好 / 7 尚可 / 6.5 偏低 / 6 不足 / 5 以下严重不足。
    "sleep": {"gte": True, "floor": 1,
              "bands": [[8.0, 10], [7.5, 9], [7.0, 8], [6.5, 6], [6.0, 4], [5.0, 2]],
              "good": 7.0},          # good 仅用于报告措辞「7h 良好线」
    # 入睡时间：改成「距 22:30 的延迟分钟」单调轴 —— 跨午夜不再跳变。
    # v1 把 00:00–06:00 全判 3 分，导致 89% 的样本同分；现在按 0/30/60/90/
    # 120/150/210 分钟七档细分，00:05 与 03:48 不再同分。
    "bedtime": {
        "late_night_max": 360,     # 00:00–06:00 = 熬夜（钟点语义，is_late_bedtime 用）
        "ok_max": 1410,            # >23:30 = 晚睡（同上）
        "anchor_min": 1350,        # 22:30 是延迟轴零点
        "floor": 2,
        "bands": [[0, 10], [30, 9], [60, 8], [90, 6], [120, 5], [150, 4], [210, 3]],
    },
    # 运动(min)：训练日更严格，且区分「完全没动」(0) 与「动了但不够」(>0) ——
    # v1 把这两种都判 2 分，覆盖了 69% 的样本。
    "exercise": {
        "train": {"bands": [[30, 10], [20, 8], [10, 6], [5, 4]], "positive": 2, "floor": 1},
        "rest": {"bands": [[20, 10], [10, 8], [5, 6]], "positive": 4, "floor": 2},
        "train_ok": 10,            # 报告措辞用（训练日至少 10min 才算「练了」）
    },
    # 饮食热量(kcal)：按「偏离目标热量的比例」打分，越贴近个人目标越准。
    # v1 是「落进 1200–2200 一律 8 分」，实测 54/74 天同分（73%）→ 死档。
    # 目标 = DIET_TARGET_KCAL（1622，由宏量目标推导）；缺失时用 fallback_target。
    "diet": {
        "fallback_target": 1700,
        "floor": 1,
        "bands": [[0.08, 10], [0.15, 8], [0.22, 6], [0.32, 4], [0.45, 2]],
        "good_low": 1200, "good_high": 2200,   # 报告措辞用（旧区间，不作判分）
    },
    # 手机屏幕(h)：从 5 档细到 9 档 —— v1 的 >10h 一档覆盖 74% 的样本。
    "phone": {"gte": False, "floor": 1,
              "bands": [[3, 10], [4, 9], [5, 8], [6, 7], [7, 6],
                        [8, 5], [9, 4], [10, 3], [11.5, 2]],
              "ideal": 4.0,            # 报告措辞用
              "bad": 10.0},            # 告警线（= 掉到 3 分及以下的临界点）
    # 健康分各子项权重（和 = 1.00；缺项时由 compute 侧重新归一）
    # 按「健康影响大小 × 个人可改变性」分配，不按分数好看与否：
    #   sleep_h 粒度最细（自动采集，实测 sd=2.61）→ 0.20
    #   sleep_quality 是主观自评且与睡时长共线（sd=0.84，信息量最低）→ 0.08
    #   exercise 影响最大且 82% 的训练日没练 → 0.26（真实反映，不为了好看下调）
    "weights": {
        "sleep_h": 0.20, "sleep_quality": 0.08, "bedtime": 0.16,
        "exercise": 0.26, "diet": 0.14, "phone": 0.16,
    },
}

# ---------------------------------------------------------------------------
# 熔断规则（可配置层）—— 任一维度持续走低时的强制提醒
#
# 用户原始定义：**单维度 <6 连续 3 天即熔断**。此前这条规则只写在文档里、
# 代码零实现（见 fuse 模块的说明）。v1.4.0 起由 `python -m review_tool fuse`
# 与 `doctor` 自动检测。
#
# 为什么另设「相对基线」：49 天样本里学习分 82% 的天数 <6、60% 正好落在最低
# 档，绝对阈值对该维度近乎恒真 —— 连续 24 天触发等于没有信息量。于是：
#   · long_run_days 连续超过 14 天 → 报告「阈值失效」，提示改用相对基线；
#   · recent_days vs baseline_days 的均值偏离，才是真正有分辨力的信号。
# ---------------------------------------------------------------------------

FUSE_RULES = {
    "threshold": 6,        # 低于此分视为「低」
    "days": 3,             # 连续 N 天低于阈值 → 熔断（用户原始定义）
    "long_run_days": 14,   # 连续超过 N 天 → 判定「阈值已失效」，改用相对基线
    "recent_days": 7,      # 相对信号：近 7 日均值
    "baseline_days": 28,   # 相对信号：与之对比的之前 28 日均值
    "drift": 1.0,          # 均值偏离达到此值才算「真的在变」
}

# 个人打卡依从率骤降告警（doctor 建议性，不影响 is_healthy）
# 近 recent_days 日完成率相对此前 baseline_days 日完成率，绝对降幅 ≥ drop 则提示。
# drop 为 0–1 比例（0.3 = 30 个百分点）。
TRACK_ADHERENCE_ALERT = {
    "recent_days": 7,
    "baseline_days": 28,
    "drop": 0.3,
}


# ---------------------------------------------------------------------------
# 外部素材源：ClickUp（可选，v1.6.0）
#
# ClickUp 是**行为跟踪的执行层**：
#   · 素材通道（``clickup``）：只 GET → 收件箱 md，不参与四维评分；
#   · 习惯快照（``habit_sync`` / ``clickup --with-habits``）：ClickUp → habit_logs
#     —— **唯一允许的 ClickUp→库写方向**（与 ``clickup-push`` 库→ClickUp 互不干扰）；
#   · 「习惯与打卡」的勾选**不得**写进复盘 md 的「一、日常打卡」——那一节只收
#     补剂 / 护肤（``PERSONAL_ITEMS``），混进去会污染 personal_tracks 的依从率。
# 映射口径、list ID 语义与日期归属（``date_closed`` 而非 ``due_date``）另见项目级
# skill ``clickup-tracking``。
#
# 不用 ClickUp 的话整段不用管 —— 没有凭据就没有 `clickup` / `habits --sync`，
# 其余功能零影响（依旧零依赖、无网络调用）。
# ---------------------------------------------------------------------------

# 凭据来源（本机，优先级从高到低）：
#   1. 环境变量 / 仓库根 ``.env``（``CLICKUP_API_KEY`` / ``CLICKUP_TEAM_ID``，M16 Settings）
#   2. ``~/.workbuddy/mcp.json`` → ``mcpServers.clickup.env``（兼容旧路径）
# ⛔ 本仓库入 git，**token 绝不写在这里**，运行时现读。
# ClickUp 端点与超时 —— v1.25.0 起纳入 Settings（与 KeepStrong 对称）：
# 代码给默认值，``.env`` / 环境变量可覆盖，测试可注入假端点。
CLICKUP_BASE_URL = SETTINGS.clickup_base_url
CLICKUP_TIMEOUT_S = SETTINGS.clickup_timeout_s

CLICKUP_MCP_PATH = os.path.join(os.path.expanduser("~"), ".workbuddy", "mcp.json")

# ClickUp 的时间戳是 UTC 毫秒；「某天完成了什么」按东八区归日。
CLICKUP_TZ_HOURS = TZ_OFFSET_HOURS  # 单一来源见文件顶部 TZ_OFFSET_HOURS

# 「隔天早上补勾」回拨（v1.12.0）
#
# 实际用法：事情当天做完，**次日早上**才一起勾选完成。若严格按 ``date_closed`` 归日，
# 前一天做的事会被系统性记到第二天 —— 实测 2026-10-14 做的 3 条（整理代办清单 /
# 每日复盘系统进行迭代 / 选股系统进行升级）是 10-15 08:41/08:46 才勾的，
# 于是 10-14 素材里「日常事务 0 条」，而用户在日历上明明看得见（日历按 due 摆）。
#
# 回拨条件（三条全满足才回拨，宁少勿多）：
#   ① 完成时刻 < 当天 ``morning_hour`` 点（默认 12:00，即「早上」窗口）；
#   ② 有 ``due_date``，且其日期 = 完成日 − N 天（1 ≤ N ≤ ``lookback_days``，默认 1 = 恰为前一天）；
#   ③ 那就回拨到该 ``due_date`` 的日期。
#
# 为什么 ② 不能省、lookback 也不能放大：2026-10-13 迁移时整批关闭了 100+ 条历史任务
# （``due`` 散在 6–9 月、集中在 11:17 前后关闭）。只看 ① 会把它们全拉回几个月前。
# 想彻底关掉回拨：把 ``morning_hour`` 或 ``lookback_days`` 设为 0。
# 回拨只影响**已完成项**的归日，不改 due / 状态，也不写回 ClickUp。
CLICKUP_REBATE = {
    "morning_hour": 12,     # 完成时刻早于当天 12:00 才算「次日早上补勾」
    "lookback_days": 1,     # due 必须落在前 1 天内（＝恰为前一天）
}

# 采集哪些 list —— 按需增删。``daily=True`` 的是默认每日素材来源。
CLICKUP_LISTS = [
    # v1.24.0：原「成长课 · 14周计划」(901422213140) 与「阅读与学习」(901422213142)
    # 两个 list 已并入本 list（原 list 已删除）—— 行为流水 + 学习进度 + 读书进度同源，
    # 课程/书名靠 ``core/learning.py`` 的主题别名分类，不再依赖独立 list。
    {"id": LIST_DAILY, "name": "日常事务", "role": "行为流水", "daily": True},
    {"id": LIST_HABITS, "name": "习惯与打卡", "role": "长期习惯", "daily": True},
    # v1.11.0：工作改为默认采集 —— 它是**当天工作产出的唯一来源**
    # （形如「李扬-2h-修复…」的工时/工单记录，含请假等工时填报）。
    # 此前 daily=False，导致 10-13（9 条）/ 10-14（2 条）等工作记录
    # 全部缺席每日素材，复盘叙事的「工作」栏只能靠用户自报。
    {"id": LIST_WORK, "name": "工作", "role": "工作产出", "daily": True},
    {"id": LIST_INCUBATOR, "name": "项目孵化", "role": "副业产出", "daily": False},
    {"id": LIST_ANNUAL, "name": "2026 年度目标", "role": "长期方向", "daily": False},
]

# 不传 ``--list`` 时采哪些（顺序即素材简报里的分组顺序）
CLICKUP_DAILY_IDS = tuple(item["id"] for item in CLICKUP_LISTS if item["daily"])

# list id -> 中文名 / 用途（渲染素材简报分组标题用）
CLICKUP_LIST_META = {item["id"]: item for item in CLICKUP_LISTS}

# 素材简报文件名前缀（落 ``每日复盘/收件箱/``；该目录不参与 ingest 扫描）
CLICKUP_INBOX_PREFIX = "clickup-素材"

# 回写通道定位（``clickup-push``）：只写这一条元任务，绝不碰其它任务。
# ``task_id`` 留空则按 list + 名字**唯一定位**；名字不唯一时再把 id 写死。
# 权威方向：复盘库 → ClickUp 下游；默认 dry-run，显式 ``--apply`` 才真写。
CLICKUP_REVIEW_TASK = {
    "list_id": LIST_HABITS,   # 习惯与打卡
    "name": "每日复盘总结",
    "task_id": None,
}

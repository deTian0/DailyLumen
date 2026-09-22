"""项目配置：路径、字段类型、个人化配置（可配置层）、评分阈值。

所有路径都相对「包目录」推导，因此无论项目放在何处都能正常工作。

本文件同时承担「可配置层」职责，小伙伴拿到本项目后**只需改本文件**即可适配自己：

- ``PROFILE``      个人作息 / 目标 / 训练日约定
- ``PERSONAL_ITEMS`` 个人打卡项定义（补剂 / 护肤 / 自定义）——解析与归一化的单一来源
- ``SCORE_THRESHOLDS`` 四维评分阈值与权重（同时驱动「AI 评价与建议」的关注点规则）

改这三处即可，无需改动模板与其余代码。
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

# 包目录（本文件所在目录 = review_tool/）
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录（仓库根 = 每日复盘计划/）
BASE_DIR = os.path.dirname(PACKAGE_DIR)

# 数据库文件
DB_PATH = os.path.join(PACKAGE_DIR, "reviews.db")

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

# 历史语雀文件来源目录（用环境变量 DAILYLUMEN_HISTORY_SRC 指定，不内置个人路径）
HISTORY_SRC_DIR = os.environ.get("DAILYLUMEN_HISTORY_SRC")

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
TEXT_FIELDS = {"weekday", "energy", "mood", "summary"}

# 星期中文（0=周一），new-day 与历史导入共用
WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]

# ---------------------------------------------------------------------------
# 个人化配置
# ---------------------------------------------------------------------------

PROFILE = {
    "name": "默认用户",
    # 早餐作息窗口（仅用于模板展示与文档说明）
    "breakfast_window": "08:00-09:00",
    # 三大营养素每日目标（g）：供「AI 评价与建议」判定摄入是否达标，留空则不检查。
    # 默认值 = 当前用户薄荷健康 App 的目标基线。
    "macro_targets": {"carbs_g": 220, "protein_g": 82, "fat_g": 46},
    # 训练日约定：0=周一 … 6=周日。用于 import-history 推算 / ingest 对空值兜底。
    "training_weekdays": [0, 1, 2, 4, 5],
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
# 评分阈值（可配置层）：默认值为当前用户的评分偏好。
# score.py 引用这些常量计算四维分；「AI 评价与建议」的文案也从这里派生，
# 因此改这里不会出现「阈值改了、文案还在说老数字」的问题。
# ---------------------------------------------------------------------------

SCORE_THRESHOLDS = {
    # 睡眠时长(h)：>=8 满分，>=7 良好，>=6.5 尚可，>=6 偏低，否则差
    "sleep": {"full": 8.0, "good": 7.0, "ok": 6.5, "low": 6.0},
    # 入睡时间(距00:00分钟)：<=360(06:00)熬夜/通宵后；<=1350(22:30)早；<=1410(23:30)尚可；否则晚
    "bedtime": {"late_night_max": 360, "early_max": 1350, "ok_max": 1410},
    # 运动(min)：训练日>=30满分/>=10尚可/否则差；非训练日>=20良好/否则一般
    "exercise": {"train_full": 30, "train_ok": 10, "normal_full": 20},
    # 饮食热量(kcal)：1200-2200 良好；1000-1200 或 2200-2600 一般；否则差
    "diet": {"good_low": 1200, "good_high": 2200, "ok_low": 1000, "ok_high": 2600},
    # 手机屏幕(h)：<=4 满分，<=6 良好，<=8 尚可，<=10 一般，否则差
    "phone": {"ideal": 4.0, "good": 6.0, "ok": 8.0, "bad": 10.0},
    # 深度工作 / 学习 / 生活投入(h) 分档：full / good / ok（低于 ok 为最低档）
    "work": {"full": 6.0, "good": 4.0, "ok": 2.0},
    "learn": {"full": 3.0, "good": 2.0, "ok": 1.0},
    "life": {"full": 3.0, "good": 2.0, "ok": 1.0},
    # 健康分各子项权重（服药依从已移出通用评分，故不在此）
    "weights": {
        "sleep_h": 0.18, "sleep_quality": 0.12, "bedtime": 0.15,
        "exercise": 0.25, "diet": 0.10, "phone": 0.15,
    },
}

"""项目配置：路径与常量。

所有路径都相对「包目录」推导，因此无论项目放在何处都能正常工作。

本文件同时承担「可配置层」职责：
- PROFILE：个人定制项（补剂方案 / 护肤 / 作息窗口），不计入通用评分。
- SCORE_THRESHOLDS：四维评分阈值与权重，默认 = 当前用户偏好，可自由调整。
小伙伴拿到本项目后，只需修改这两处即可适配自己，无需改动模板与代码。
"""
from __future__ import annotations

import os

# 包目录（本文件所在目录 = review_tool/）
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))

# 项目根目录（仓库根 = 每日复盘计划/）
BASE_DIR = os.path.dirname(PACKAGE_DIR)

# 数据库文件
DB_PATH = os.path.join(PACKAGE_DIR, "reviews.db")

# 建表脚本
SCHEMA_PATH = os.path.join(PACKAGE_DIR, "schema.sql")

# 每日复盘 md 输入目录（你每天把复盘文件丢这里）
INPUT_DIR = os.path.join(BASE_DIR, "每日复盘")

# 自动生成复盘的输出子目录（区别于手写/历史复盘，避免新旧混放）
GENERATED_DIR = os.path.join(INPUT_DIR, "复盘")

# 收件箱（用户投放原始简报/截图的目录，入库扫描时跳过）
INBOX_DIR = os.path.join(INPUT_DIR, "收件箱")

# 复盘模板
TEMPLATE_PATH = os.path.join(BASE_DIR, "每日复盘模板.md")

# 历史语雀文件来源目录（必须用环境变量 DAILYLUMEN_HISTORY_SRC 指定，不内置个人路径）
HISTORY_SRC_DIR = os.environ.get("DAILYLUMEN_HISTORY_SRC")

# 四维评分维度
DIMENSIONS = ["health_score", "work_score", "learn_score", "life_score"]

# 字段类型映射：用于解析时转换
INT_FIELDS = {
    "sleep_quality", "exercise_min", "diet_kcal", "meals_count",
    "health_score", "work_score", "learn_score", "life_score",
}
FLOAT_FIELDS = {"sleep_h", "phone_h", "deepwork_h", "learn_h", "life_h"}
BOOL_FIELDS = {
    "training_day", "commute_done", "breakfast_on_time",
}
TEXT_FIELDS = {"weekday", "energy", "mood", "summary"}


# ---------------------------------------------------------------------------
# 个人化配置（可配置层）：补剂方案 / 护肤 / 作息窗口等「个人定制项」。
# 这些项不计入通用评分，单独统计于 personal_tracks 表。
# 小伙伴使用时只需修改此处，无需改动模板与代码。默认值 = 当前用户设定。
# ---------------------------------------------------------------------------
PROFILE = {
    "name": "默认用户",
    "supplements": {
        "morning": ["CoQ10 ×1", "Exia 早3"],
        "noon": ["复合维生素B族 ×1", "Move Free 红色 ×1"],
        "evening": ["Exia 晚3", "Move Free 红色 ×1"],
    },
    "skincare": ["护肤"],
    "breakfast_window": "08:00-09:00",
}


# ---------------------------------------------------------------------------
# 评分阈值（可配置层）：默认值为当前用户的评分偏好。
# score.py 引用这些常量计算四维分；修改即可调整评分标准，无需改代码。
# ---------------------------------------------------------------------------
SCORE_THRESHOLDS = {
    # 睡眠时长(h)：>=8 满分，>=7 良好，>=6.5 尚可，>=6 偏低，否则差
    "sleep": {"full": 8.0, "good": 7.0, "ok": 6.5, "low": 6.0},
    # 入睡时间(距00:00分钟)：<=300(05:00)熬夜；<=1350(22:30)早；<=1410(23:30)尚可；否则晚
    "bedtime": {"late_night_max": 300, "early_max": 1350, "ok_max": 1410},
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


def system_score_from(row: dict) -> float | None:
    """根据四维评分算系统分；任一缺失返回 None。"""
    vals = [row.get(d) for d in DIMENSIONS]
    if all(v is not None for v in vals):
        return round(sum(vals) / len(vals), 2)
    return None

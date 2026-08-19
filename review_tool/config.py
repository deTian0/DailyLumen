"""项目配置：路径与常量。

所有路径都相对「包目录」推导，因此无论项目放在何处都能正常工作。
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

# 历史语雀文件来源目录（可用环境变量 DAILYLUMEN_HISTORY_SRC 覆盖）
HISTORY_SRC_DIR = os.environ.get(
    "DAILYLUMEN_HISTORY_SRC",
    r"C:\Users\63516\Desktop\新建文件夹",
)

# 四维评分维度
DIMENSIONS = ["health_score", "work_score", "learn_score", "life_score"]

# 字段类型映射：用于解析时转换
INT_FIELDS = {
    "sleep_quality", "exercise_min", "diet_kcal", "meals_count",
    "health_score", "work_score", "learn_score", "life_score",
}
FLOAT_FIELDS = {"sleep_h", "phone_h", "deepwork_h", "learn_h", "life_h"}
BOOL_FIELDS = {
    "training_day", "supps_done", "commute_done", "breakfast_on_time",
}
TEXT_FIELDS = {"weekday", "energy", "mood", "summary"}


def system_score_from(row: dict) -> float | None:
    """根据四维评分算系统分；任一缺失返回 None。"""
    vals = [row.get(d) for d in DIMENSIONS]
    if all(v is not None for v in vals):
        return round(sum(vals) / len(vals), 2)
    return None

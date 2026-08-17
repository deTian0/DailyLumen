"""项目配置：路径与常量。"""
import os

# 项目根目录 (本文件所在目录)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 数据库路径
DB_PATH = os.path.join(BASE_DIR, "reviews.db")

# 每日复盘 md 输入目录 (你每天把复盘文件丢这里)
INPUT_DIR = os.path.join(os.path.dirname(BASE_DIR), "每日复盘")

# 四维评分维度
DIMENSIONS = ["health_score", "work_score", "learn_score", "life_score"]

# 字段类型映射：用于解析时转换
INT_FIELDS = {
    "sleep_quality", "exercise_min", "diet_kcal", "meals_count",
    "health_score", "work_score", "learn_score", "life_score",
}
FLOAT_FIELDS = {"sleep_h", "phone_h", "deepwork_h"}
BOOL_FIELDS = {
    "training_day", "supps_done", "commute_done", "breakfast_on_time",
}
TEXT_FIELDS = {"weekday", "energy", "mood", "summary"}


def system_score_from(row):
    """根据四维评分算系统分；任一缺失返回 None。"""
    vals = [row.get(d) for d in DIMENSIONS]
    if all(v is not None for v in vals):
        return round(sum(vals) / len(vals), 2)
    return None

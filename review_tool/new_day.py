"""一键生成当天复盘文件：从模板复制 -> 填好日期/星期 -> 清空示例值。

用法:
    python -m review_tool new-day            # 生成今天的 YYYY-MM-DD.md
    python -m review_tool new-day 2026-08-20 # 生成指定日期
"""
from __future__ import annotations

import os
import re
import sys
from datetime import date, datetime

from .config import INPUT_DIR, TEMPLATE_PATH

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]

# 清空示例值时保留键名的字段
KNOWN_KEYS = [
    "训练日", "睡眠时长_h", "睡眠质量", "入睡时间", "补剂完成",
    "运动时长_min", "饮食热量_kcal", "三餐情况", "早餐按时", "手机屏幕_h",
    "深度工作_h", "学习投入_h", "生活投入_h", "一句话总结",
]


def generate(target_date: date | None = None) -> str:
    """从模板生成指定日期的复盘文件，返回输出路径（已存在则跳过）。"""
    if target_date is None:
        target_date = date.today()
    iso = target_date.isoformat()
    wd = WEEKDAY_CN[target_date.weekday()]

    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 1) 填日期/星期
    content = content.replace("YYYY-MM-DD", iso)
    content = content.replace("星期X", wd)
    content = re.sub(r"(星期: )\S*", f"\\g<1>{wd}", content)
    # 2) 日期行
    content = re.sub(r"(日期: )\S*", f"\\g<1>{iso}", content)
    # 3) 清空示例数值
    for k in KNOWN_KEYS:
        content = re.sub(rf"({re.escape(k)}: )[^\n]*", r"\g<1>", content)
    # 4) 打卡全部清为未勾选
    content = re.sub(r"- \[x\]", "- [ ]", content)
    # 5) 正文示例文字清空
    content = re.sub(r"1\. 模型透传.*?\n2\. 为灵日志.*?\n3\. 用 WorkBuddy.*?\n",
                     "1. \n2. \n3. \n", content, flags=re.S)
    content = re.sub(r"- 23:00 手机放客厅.*?\n", "- \n", content)
    content = re.sub(r"1\. 周三训练日.*?\n2\. 控制番茄小说.*?\n3\. 深度工作保持 5h.*?\n",
                     "1. \n2. \n3. \n", content, flags=re.S)

    out = os.path.join(INPUT_DIR, f"{iso}.md")
    if os.path.exists(out):
        print(f"已存在, 跳过: {out}")
        return out
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return out


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    d = datetime.strptime(argv[0], "%Y-%m-%d").date() if argv else date.today()
    out = generate(d)
    print(f"已生成: {out}")
    print("下一步: 打开填数值 -> python -m review_tool ingest -> python -m review_tool month")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""一键生成当天复盘文件: 从模板复制 -> 填好日期/星期 -> 清空示例值。

用法:
    python new_day.py              # 生成今天的 YYYY-MM-DD.md
    python new_day.py 2026-08-20   # 生成指定日期
    python new_day.py --weekday    # 顺带标出周几是训练日? (默认留空)
"""
import os
import sys
import re
import shutil
from datetime import date, datetime
from config import INPUT_DIR

TEMPLATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "每日复盘模板.md")

WEEKDAY_CN = ["一", "二", "三", "四", "五", "六", "日"]


def main():
    if len(sys.argv) > 1:
        d = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
    else:
        d = date.today()

    # 读模板
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 1) 填日期/星期
    content = content.replace("YYYY-MM-DD", d.isoformat())
    content = content.replace("星期X", WEEKDAY_CN[d.weekday()])
    # 数据块内 "星期: X" (模板清空后为 "星期: ") -> 当天 (用 \S* 兼容空值)
    content = re.sub(r"(星期: )\S*", f"\\g<1>{WEEKDAY_CN[d.weekday()]}", content)

    # 2) 日期行 (数据块内 "日期: " 清空) -> 当天
    content = re.sub(r"(日期: )\S*", f"\\g<1>{d.isoformat()}", content)

    # 3) 清空示例数值: 数据块里 `键: 示例值` -> `键: ` (留空)
    #    只清已知字段, 保留键名
    known_keys = [
        "训练日", "睡眠时长_h", "睡眠质量", "入睡时间", "补剂完成",
        "运动时长_min", "饮食热量_kcal", "三餐情况", "早餐按时", "手机屏幕_h",
        "深度工作_h", "学习投入_h", "生活投入_h", "一句话总结",
    ]
    for k in known_keys:
        content = re.sub(rf"({re.escape(k)}: )[^\n]*", r"\g<1>", content)

    # 4) 打卡全部清为未勾选
    content = re.sub(r"- \[x\]", "- [ ]", content)

    # 5) 正文示例文字清空 (三件事/改进点/明日Top3 -> 留空列表)
    content = re.sub(r"1\. 模型透传.*?\n2\. 为灵日志.*?\n3\. 用 WorkBuddy.*?\n",
                     "1. \n2. \n3. \n", content, flags=re.S)
    content = re.sub(r"- 23:00 手机放客厅.*?\n", "- \n", content)
    content = re.sub(r"1\. 周三训练日.*?\n2\. 控制番茄小说.*?\n3\. 深度工作保持 5h.*?\n",
                     "1. \n2. \n3. \n", content, flags=re.S)

    # 写文件
    out = os.path.join(INPUT_DIR, f"{d.isoformat()}.md")
    if os.path.exists(out):
        print(f"已存在, 跳过: {out}")
        return
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"已生成: {out}")
    print("下一步: 打开填数值 -> python ingest.py -> python analyze.py month")


if __name__ == "__main__":
    main()

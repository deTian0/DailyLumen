"""总管家编排：晨间 brief / 夜间复盘指引 / 周度六段合一。

用法:
    python -m review_tool steward --slot morning [YYYY-MM-DD]
    python -m review_tool steward --slot evening [YYYY-MM-DD]
    python -m review_tool steward --slot week [ISO周|YYYY-MM-DD]
    python -m review_tool steward --slot morning --json
    python -m review_tool steward --slot morning --todo "任务A" --todo "任务B"

设计（M14 / v1.18.0）
-------------------
编排层**只调用**现有模块的 ``collect`` / ``find_fuses`` / ``fetch_day`` 等，
**不重复实现**任何评分 / 熔断 / 缺口 / 依从率计算（R1）。
每个数字在输出里标注溯源（``source=…``）。
⛔ 不新增定时任务 —— 一切按需 CLI / skill 触发。
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta

from ..storage.db import init_db
from . import analyze, body, coach, fuse, habits, nutrition, tutor
from .ai_review import fetch_day


def _week_span(conn, iso_week: int) -> tuple[str, str] | None:
    """本周库内首末日（读库，非计算）。与 analyze 周窗口同源 SQL。"""
    row = conn.execute(
        "SELECT MIN(date), MAX(date) FROM daily_reviews WHERE iso_week=?",
        (iso_week,),
    ).fetchone()
    if not row or row[0] is None:
        return None
    return row[0], row[1]

SLOTS = ("morning", "evening", "week")

_WEEKDAY_CN = ("一", "二", "三", "四", "五", "六", "日")

# 溯源标签：编排输出里每个数字区块都挂一个，便于人工对照 CLI
_SRC = {
    "scores": "ai_review.fetch_day / fuse.find_fuses",
    "fuse": "fuse.find_fuses（等同 CLI fuse）",
    "training": "调用方传入的今日课名；未传入则不判断（不打网、不按星期）",
    "diet": "nutrition.collect → config.PROFILE[macro_targets]",
    "todos": "clickup（进行中；CLI: clickup --stdout）",
    "intake": "skill daily-review-intake",
    "body": "body.collect（等同 CLI body）",
    "coach": "coach.collect（等同 CLI coach）",
    "nutrition": "nutrition.collect（等同 CLI nutrition）",
    "habits": "habits.collect（等同 CLI habits）",
    "tutor": "tutor.collect（等同 CLI tutor）",
    "week4d": "analyze.collect（等同 CLI week）",
}


def _yesterday(as_of: str) -> str:
    return (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()


def _resolve_as_of(conn, as_of: str | None) -> str:
    if as_of:
        return as_of
    row = conn.execute("SELECT MAX(date) FROM daily_reviews").fetchone()
    return row[0] if row and row[0] else date.today().isoformat()


def _resolve_iso_week(conn, token: str | None) -> int:
    """ISO 周：显式周号 / 日期锚点 / 库内最近一天。"""
    if token is None:
        as_of = _resolve_as_of(conn, None)
        return date.fromisoformat(as_of).isocalendar()[1]
    if token.isdigit() and len(token) <= 2:
        return int(token)
    if len(token) == 10 and token[4] == "-" and token[7] == "-":
        return date.fromisoformat(token).isocalendar()[1]
    # 允许 "42" 以外的纯数字周号（如 01）
    try:
        return int(token)
    except ValueError as exc:
        raise ValueError(f"无法解析 ISO 周: {token!r}") from exc


def _today_training(as_of: str, today_plan: str | None = None) -> dict:
    """晨间「今天练什么」。

    当天的 completed 往往还不存在，禁止用「还没完成记录」或星期推出休息/训练。
    只有调用方传入已拉取的今日课名称时才打印课名；默认不打网。
    """
    d = date.fromisoformat(as_of)
    wd = d.weekday()
    name = (today_plan or "").strip() or None
    if name:
        label = name
        judged = True
        hint = None
        source = "调用方传入的今日课名"
    else:
        label = "今日是否训练：未同步练练计划，不判断"
        judged = False
        hint = "python -m review_tool keepstrong --type plan"
        source = _SRC["training"]
    return {
        "date": as_of,
        "weekday": wd,
        "weekday_cn": f"星期{_WEEKDAY_CN[wd]}",
        "is_training_day": None,
        "judged": judged,
        "plan_name": name,
        "label": label,
        "hint": hint,
        "source": source,
    }


def collect_morning(
    conn,
    *,
    as_of: str | None = None,
    todos: list[str] | None = None,
    today_plan: str | None = None,
) -> dict:
    """晨间 brief 数据：昨日四维+熔断 → 今日训练 → 饮食目标 → 待办 Top 3。"""
    as_of = _resolve_as_of(conn, as_of)
    yday = _yesterday(as_of)
    day = fetch_day(conn, yday)
    fuse_data = fuse.find_fuses(conn)
    coach_data = coach.collect(conn, as_of=as_of)
    nutri = nutrition.collect(conn, as_of=as_of)
    training = _today_training(as_of, today_plan)

    scores = None
    if day:
        scores = {
            "date": yday,
            "health_score": day.get("health_score"),
            "work_score": day.get("work_score"),
            "learn_score": day.get("learn_score"),
            "life_score": day.get("life_score"),
            "system_score": day.get("system_score"),
            "source": _SRC["scores"],
        }

    abs_fused = [
        {"label": it["label"], "run": it["run"], "since": it["since"]}
        for it in (fuse_data.get("absolute") or [])
    ]

    todo_list = list(todos) if todos is not None else []
    return {
        "slot": "morning",
        "as_of": as_of,
        "yesterday": yday,
        "scores": scores,
        "fuse": {
            "as_of": fuse_data.get("as_of"),
            "absolute_count": len(abs_fused),
            "absolute": abs_fused,
            "source": _SRC["fuse"],
        },
        "training": training,
        "coach_completion": {
            "completed": coach_data["completion"]["completed"],
            "planned": coach_data["completion"]["planned"],
            "ratio": coach_data["completion"]["ratio"],
            "source": _SRC["coach"],
        },
        "diet_targets": {
            **dict(nutri.get("targets") or {}),
            "source": _SRC["diet"],
        },
        "todos": {
            "items": todo_list[:3],
            "hint": (
                None if todo_list
                else "跑 `python -m review_tool clickup --stdout`，取「进行中」作 Top 3"
            ),
            "source": _SRC["todos"],
        },
        "sources": list(_SRC.values()),
    }


def collect_evening(conn, *, as_of: str | None = None) -> dict:
    """夜间复盘指引：挂 daily-review-intake + 体征/训练/饮食/学习回填命令。"""
    as_of = _resolve_as_of(conn, as_of)
    day = fetch_day(conn, as_of)
    steps = [
        {
            "id": "intake",
            "title": "走 daily-review-intake 全流程",
            "cmd": None,
            "note": "加载 skill `daily-review-intake`：确认归属日 → 抽素材 → 写 md → ingest → sync-docs → AI 评价 → 再 ingest",
            "source": _SRC["intake"],
        },
        {
            "id": "clickup",
            "title": "拉 ClickUp 当日素材（可选）",
            "cmd": f"python -m review_tool clickup {as_of}",
            "note": "习惯另用 --with-habits；不进 personal_tracks",
            "source": "CLI clickup",
        },
        {
            "id": "body",
            "title": "体征截图回填",
            "cmd": "python -m review_tool body",
            "note": "md 数据块填 体重_kg / 体脂率 / 腰围_cm → ingest（见 intake §3.5）",
            "source": _SRC["body"],
        },
        {
            "id": "training",
            "title": "练练同步训练日与明细",
            "cmd": (
                f"python -m review_tool keepstrong --date {as_of}"
                " --write --ingest"
            ),
            "note": (
                "对象日=被复盘日（执行日的昨日）。只取 completed；"
                "先落 md 再入库（见 intake §3.6）"
            ),
            "source": "CLI keepstrong",
        },
        {
            "id": "nutrition",
            "title": "饮食 / 薄荷回填",
            "cmd": f"python -m review_tool nutrition {as_of}",
            "note": "数据块宏量 → ingest → nutrition 看缺口（见 intake §3.6）",
            "source": _SRC["nutrition"],
        },
        {
            "id": "learning",
            "title": "学习记录回填（可选）",
            "cmd": f"python -m review_tool tutor {as_of}",
            "note": "附录 · 学习记录 → ingest（见 intake §3.7）",
            "source": _SRC["tutor"],
        },
        {
            "id": "doctor",
            "title": "收尾体检",
            "cmd": "python -m review_tool doctor",
            "note": "对账 / 熔断 / R3；写评价前看 [熔断检测]",
            "source": "CLI doctor",
        },
    ]
    return {
        "slot": "evening",
        "as_of": as_of,
        "day_in_db": day is not None,
        "steps": steps,
        "sources": [_SRC["intake"], _SRC["body"], _SRC["coach"],
                    _SRC["nutrition"], _SRC["tutor"], "CLI doctor / clickup"],
    }


def collect_week(
    conn,
    *,
    iso_week: int | None = None,
    as_of: str | None = None,
) -> dict:
    """周度六段：四维 + 体征 + 训练 + 饮食 + 习惯 + 学习。"""
    if iso_week is None:
        anchor = _resolve_as_of(conn, as_of)
        iso_week = date.fromisoformat(anchor).isocalendar()[1]

    week4d = analyze.collect(conn, "iso_week=?", (iso_week,), f"ISO 周 {iso_week}")
    span = _week_span(conn, iso_week)
    week_end = span[1] if span else _resolve_as_of(conn, as_of)

    body_data = body.collect(conn)
    coach_data = coach.collect(conn, as_of=week_end)
    nutri = nutrition.collect(conn, as_of=week_end)
    habits_data = habits.collect(conn, as_of=week_end)
    tutor_data = tutor.collect(conn, as_of=week_end, rebuild=False)

    return {
        "slot": "week",
        "iso_week": iso_week,
        "span": {"start": span[0], "end": span[1]} if span else None,
        "week_end": week_end,
        "four_dims": {
            "data": week4d,
            "source": _SRC["week4d"],
        },
        "body": {
            "latest": body_data.get("latest"),
            "ma7": body_data.get("ma7"),
            "weekly_delta": body_data.get("weekly_delta"),
            "bmi": body_data.get("bmi"),
            "count": body_data.get("count"),
            "source": _SRC["body"],
        },
        "training": {
            "completion": coach_data.get("completion"),
            "structure": (week4d or {}).get("training_structure") if week4d else None,
            "source": _SRC["coach"],
        },
        "nutrition": {
            "targets": nutri.get("targets"),
            "day_gap": nutri.get("day_gap"),
            "window_gap": nutri.get("window_gap"),
            "macros_week": (week4d or {}).get("macros") if week4d else None,
            "source": _SRC["nutrition"],
        },
        "habits": {
            "adherence": habits_data.get("adherence"),
            "gaps": habits_data.get("gaps"),
            "source": _SRC["habits"],
        },
        "learning": {
            "week": tutor_data.get("week"),
            "due_today": tutor_data.get("due_today"),
            "overdue": tutor_data.get("overdue"),
            "source": _SRC["tutor"],
        },
        "sources": [
            _SRC["week4d"], _SRC["body"], _SRC["coach"],
            _SRC["nutrition"], _SRC["habits"], _SRC["tutor"],
        ],
    }


def collect(
    conn,
    *,
    slot: str,
    as_of: str | None = None,
    iso_week: int | None = None,
    todos: list[str] | None = None,
    today_plan: str | None = None,
) -> dict:
    if slot not in SLOTS:
        raise ValueError(f"未知 slot: {slot!r}（须为 {'|'.join(SLOTS)}）")
    if slot == "morning":
        return collect_morning(
            conn, as_of=as_of, todos=todos, today_plan=today_plan,
        )
    if slot == "evening":
        return collect_evening(conn, as_of=as_of)
    return collect_week(conn, iso_week=iso_week, as_of=as_of)


def _fmt_score(v) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def render_morning(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 总管家 · 晨间 brief")
    L.append("=" * 52)
    L.append(f"今日: {data['as_of']} ｜ 回顾昨日: {data['yesterday']}")
    L.append("")

    L.append("---- 1. 昨日四维 + 熔断 ----")
    L.append(f"  source={_SRC['scores']}")
    sc = data.get("scores")
    if not sc:
        L.append(f"  （库中无 {data['yesterday']} 记录）")
    else:
        L.append(
            f"  健康 {_fmt_score(sc['health_score'])} ｜ "
            f"工作 {_fmt_score(sc['work_score'])} ｜ "
            f"学习 {_fmt_score(sc['learn_score'])} ｜ "
            f"生活 {_fmt_score(sc['life_score'])} ｜ "
            f"系统 {_fmt_score(sc['system_score'])}"
        )
    fd = data["fuse"]
    L.append(f"  source={fd['source']}")
    if fd["absolute_count"] == 0:
        L.append("  熔断: 无维度触发")
    else:
        for it in fd["absolute"]:
            tail = "（长期低位·阈值失效）" if it.get("long_run") else ""
            L.append(
                f"  熔断: {it['label']} 连续 {it['run']} 天"
                f"（自 {it['since']}）{tail}"
            )
    L.append("")

    L.append("---- 2. 今日训练课 ----")
    tr = data["training"]
    L.append(f"  source={tr['source']}")
    L.append(f"  {tr['weekday_cn']} · {tr['label']}")
    if tr.get("hint"):
        L.append(f"  {tr['hint']}")
    cc = data["coach_completion"]
    L.append(f"  source={cc['source']}")
    if cc["planned"] is None:
        L.append(
            f"  本周完成 {cc['completed']} 课（计划课次未配置，不判加量）"
        )
    else:
        L.append(
            f"  本周完成 {cc['completed']}/{cc['planned']} 课"
            f"（比率 {cc['ratio']}）"
        )
    L.append("")

    L.append("---- 3. 饮食目标 ----")
    dt = data["diet_targets"]
    L.append(f"  source={dt['source']}")
    L.append(
        f"  碳水 {dt.get('carbs_g', '—')}g ｜ "
        f"蛋白 {dt.get('protein_g', '—')}g ｜ "
        f"脂肪 {dt.get('fat_g', '—')}g"
    )
    L.append("")

    L.append("---- 4. 待办 Top 3 ----")
    td = data["todos"]
    L.append(f"  source={td['source']}")
    items = td.get("items") or []
    if items:
        for i, t in enumerate(items, 1):
            L.append(f"  {i}. {t}")
    else:
        L.append(f"  （未注入）{td.get('hint') or ''}")
    L.append("")
    L.append("编排层无独立计算；数字均可对照上列 source 的 CLI/模块复核。")
    return "\n".join(L)


def render_evening(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 总管家 · 夜间复盘编排")
    L.append("=" * 52)
    L.append(f"归属日: {data['as_of']} ｜ 库中已有记录: "
             f"{'是' if data['day_in_db'] else '否'}")
    L.append(f"source={_SRC['intake']}")
    L.append("")
    L.append("按序执行（素材靠手动投递，无定时任务）：")
    L.append("")
    for i, step in enumerate(data["steps"], 1):
        L.append(f"{i}. {step['title']}")
        L.append(f"   source={step['source']}")
        if step.get("cmd"):
            L.append(f"   $ {step['cmd']}")
        if step.get("note"):
            L.append(f"   · {step['note']}")
        L.append("")
    L.append("细节 SOP 见 skill `daily-review-intake` / `life-steward-daily`。")
    return "\n".join(L)


def render_week(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append(f"DailyLumen 总管家 · 周度报告（ISO 周 {data['iso_week']}）")
    L.append("=" * 52)
    span = data.get("span")
    if span:
        L.append(f"窗口: {span['start']} ~ {span['end']}")
    L.append("")

    # 1 四维
    L.append("==== 1. 四维 ====")
    sec = data["four_dims"]
    L.append(f"  source={sec['source']}")
    w = sec.get("data")
    if not w:
        L.append("  （本周无 daily_reviews）")
    else:
        L.append(f"  天数 {w['days']} ｜ 系统均 {_fmt_score(w['system_avg'])}")
        bits = " ｜ ".join(
            f"{k} {_fmt_score(v)}" for k, v in (w.get("dims") or {}).items()
        )
        L.append(f"  {bits}")
    L.append("")

    # 2 体征
    L.append("==== 2. 体征 ====")
    b = data["body"]
    L.append(f"  source={b['source']}")
    latest = b.get("latest")
    if not latest:
        L.append("  （尚无 body_metrics；CLI: body）")
    else:
        L.append(
            f"  最新 {latest['date']}: "
            f"体重 {latest.get('weight_kg') if latest.get('weight_kg') is not None else '—'} kg"
            f" ｜ BMI {_fmt_score(b.get('bmi'))}"
            f" ｜ 7 日均 {_fmt_score(b.get('ma7'))}"
            f" ｜ 周变化 {_fmt_score(b.get('weekly_delta'))}"
        )
    L.append("")

    # 3 训练
    L.append("==== 3. 训练 ====")
    t = data["training"]
    L.append(f"  source={t['source']}")
    cc = t.get("completion") or {}
    if cc.get("planned") is None:
        L.append(
            f"  本周完成 {cc.get('completed', '—')} 课"
            f"（计划课次未配置，不判加量）"
        )
    else:
        L.append(
            f"  本周完成 {cc.get('completed', '—')}/{cc.get('planned', '—')} 课"
            f"（比率 {cc.get('ratio', '—')}）"
        )
    ts = t.get("structure") or {}
    if ts.get("sessions"):
        L.append(f"  明细: {ts['sessions']} 课 / {ts.get('items', 0)} 条")
    else:
        L.append("  （无 training_sessions；CLI: coach）")
    L.append("")

    # 4 饮食
    L.append("==== 4. 饮食 ====")
    n = data["nutrition"]
    L.append(f"  source={n['source']}")
    tg = n.get("targets") or {}
    L.append(
        f"  目标: 碳水 {tg.get('carbs_g', '—')}g / "
        f"蛋白 {tg.get('protein_g', '—')}g / "
        f"脂肪 {tg.get('fat_g', '—')}g"
    )
    macros = n.get("macros_week")
    if macros:
        L.append(
            f"  周宏量日均（{macros.get('days', '—')} 天）: "
            f"碳水 {macros.get('carbs_g', '—')}g ｜ "
            f"脂肪 {macros.get('fat_g', '—')}g ｜ "
            f"蛋白 {macros.get('protein_g', '—')}g"
        )
    else:
        L.append("  （本周无宏量记录；CLI: nutrition）")
    L.append("")

    # 5 习惯
    L.append("==== 5. 习惯 ====")
    h = data["habits"]
    L.append(f"  source={h['source']}")
    items = ((h.get("adherence") or {}).get("items")) or []
    if not items:
        L.append("  （尚无 habit_logs；CLI: habits / clickup --with-habits）")
    else:
        for it in items:
            rate = it.get("adherence")
            pct = f"{rate * 100:.1f}%" if rate is not None else "—"
            L.append(
                f"  {it['habit_key']}: {pct}"
                f"（{it['done']}/{it['recorded']}）"
            )
    gaps = h.get("gaps") or []
    if gaps:
        for g in gaps:
            L.append(
                f"  ! 断更 {g['habit_key']} 连续 {g['gap_days']} 天"
            )
    L.append("")

    # 6 学习
    L.append("==== 6. 学习 ====")
    learn = data["learning"]
    L.append(f"  source={learn['source']}")
    L.extend(tutor.week_section_lines(learn.get("week") or {}))
    due_n = len(learn.get("due_today") or [])
    od_n = len(learn.get("overdue") or [])
    L.append(f"  待复习 {due_n} ｜ 逾期 {od_n}（详情 CLI: tutor）")
    L.append("")
    L.append("六段数字均可对照各 source CLI 复核；编排层无独立计算。")
    return "\n".join(L)


def render(data: dict) -> str:
    slot = data.get("slot")
    if slot == "morning":
        return render_morning(data)
    if slot == "evening":
        return render_evening(data)
    if slot == "week":
        return render_week(data)
    raise ValueError(f"未知 slot: {slot!r}")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法: python -m review_tool steward --slot morning|evening|week")
        print("      [YYYY-MM-DD|ISO周] [--json] [--todo TEXT]... [--plan 课名]")
        print("  morning  昨日四维+熔断 → 今日训练 → 饮食目标 → 待办 Top 3")
        print("  evening  挂 daily-review-intake + 体征/训练/饮食回填指引")
        print("  week     四维+体征+训练+饮食+习惯+学习 六段合一")
        print("编排只调用现有模块；无定时任务；数字可溯源。")
        return 0

    as_json = "--json" in argv
    slot = None
    todos: list[str] = []
    today_plan = None
    positional: list[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--slot" and i + 1 < len(argv):
            slot = argv[i + 1]
            i += 2
            continue
        if a.startswith("--slot="):
            slot = a.split("=", 1)[1]
            i += 1
            continue
        if a == "--todo" and i + 1 < len(argv):
            todos.append(argv[i + 1])
            i += 2
            continue
        if a.startswith("--todo="):
            todos.append(a.split("=", 1)[1])
            i += 1
            continue
        if a == "--plan" and i + 1 < len(argv):
            today_plan = argv[i + 1]
            i += 2
            continue
        if a.startswith("--plan="):
            today_plan = a.split("=", 1)[1]
            i += 1
            continue
        if a in ("--json",):
            i += 1
            continue
        if a.startswith("--"):
            print(f"未知参数: {a}", file=sys.stderr)
            return 2
        positional.append(a)
        i += 1

    if slot is None:
        # 允许位置参数首项直接写 slot
        if positional and positional[0] in SLOTS:
            slot = positional.pop(0)
        else:
            print("须指定 --slot morning|evening|week", file=sys.stderr)
            return 2
    if slot not in SLOTS:
        print(f"未知 slot: {slot}（须为 {'|'.join(SLOTS)}）", file=sys.stderr)
        return 2

    token = positional[0] if positional else None
    conn = init_db()
    try:
        if slot == "week":
            try:
                iso_week = _resolve_iso_week(conn, token)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 2
            data = collect(conn, slot="week", iso_week=iso_week)
        else:
            as_of = None
            if token and len(token) == 10 and token[4] == "-" and token[7] == "-":
                as_of = token
            elif token:
                print(f"日期须为 YYYY-MM-DD，得到: {token}", file=sys.stderr)
                return 2
            data = collect(
                conn,
                slot=slot,
                as_of=as_of,
                todos=todos or None,
                today_plan=today_plan,
            )
    finally:
        conn.close()

    if as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    else:
        print(render(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

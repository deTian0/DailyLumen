"""学习 / 复习报告：今日待复习 + 本周主题 / 投入 / 产出物（独立指标区）。

用法:
    python -m review_tool tutor
    python -m review_tool tutor --json
    python -m review_tool tutor 2026-10-15

不参与四维（G5）。「讲解 / 出题」不写代码——那是 AI 现场能力。
F2：``learn_h`` 投入兜底 + 双源书单旁证（微信读书 / ClickUp，软失败）。
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta

from ..config import LEARNING_LIST_IDS, LEARNING_TOPICS, LEARNING_WEEK_RULES, SPACED_REPEAT
from ..core.learning import classify_hours_source, due_status, week_rollup
from ..storage.db import (
    init_db,
    load_learning_logs,
    load_review_queue,
    rebuild_review_queue,
)

# ClickUp 书/课标题启发式（日常事务 list 噪音过滤）
_BOOKLIST_EXTRA_HINTS = (
    "书", "读书", "阅读", "课", "章节", "成长课", "微信读书", "墨墨",
)


def _iso_week_bounds(as_of: str) -> tuple[str, str]:
    """锚点日所在 ISO 周的周一 / 周日（含）。"""
    d = datetime.strptime(as_of, "%Y-%m-%d").date()
    start = d - timedelta(days=d.weekday())
    end = start + timedelta(days=6)
    return start.isoformat(), end.isoformat()


def _load_learn_h_rows(conn, start: str, end: str) -> list[dict]:
    """周窗内 ``daily_reviews.learn_h``（reports 层 SQL；core 零 I/O）。"""
    rows = conn.execute(
        "SELECT date, learn_h FROM daily_reviews "
        "WHERE date BETWEEN ? AND ? ORDER BY date",
        (start, end),
    ).fetchall()
    return [{"date": r[0], "learn_h": r[1]} for r in rows]


def enrich_week_hours_from_logs(
    week: dict,
    week_logs: list[dict],
    learn_h_rows: list[dict],
) -> dict:
    """把 ``classify_hours_source`` 字段并入 week 副本。"""
    log_dates = {
        r["date"] for r in week_logs
        if r.get("date") and r.get("minutes") is not None
    }
    hours = classify_hours_source(
        logs_minutes=week.get("total_minutes"),
        log_dates_with_minutes=log_dates,
        learn_h_rows=learn_h_rows,
    )
    out = dict(week)
    out.update(hours)
    return out


def _booklist_hint_terms() -> list[str]:
    terms: list[str] = list(_BOOKLIST_EXTRA_HINTS)
    for t in LEARNING_TOPICS or []:
        if t.get("key") in ("reading", "growth_course"):
            terms.append(t.get("label") or "")
            terms.extend(t.get("aliases") or [])
    return [x for x in terms if x]


def _title_matches_booklist(name: str, terms: list[str]) -> bool:
    n = (name or "").casefold()
    if not n:
        return False
    return any(term.casefold() in n for term in terms if term)


def _empty_booklist_side(*, message: str, error_kind: str | None = None,
                        enabled: bool = True) -> dict:
    return {
        "checked": False,
        "enabled": enabled,
        "titles": [],
        "message": message,
        "error_kind": error_kind,
    }


def weread_booklist_hint(
    *,
    as_of: str,
    max_n: int | None = None,
    client=None,
    env=None,
) -> dict:
    """微信读书旁证：本周读得最多的书 + 书架近读书名。失败不抛。"""
    rules = LEARNING_WEEK_RULES or {}
    if not rules.get("weread_enabled", True):
        return _empty_booklist_side(
            message="书单旁证（微信读书）：已关闭", enabled=False,
        )
    n = int(max_n if max_n is not None else rules.get("booklist_max") or 10)
    try:
        from ..integrations.flags import is_enabled
        if not is_enabled("weread"):
            return _empty_booklist_side(
                message="书单旁证（微信读书）：集成已关闭", enabled=False,
            )
    except Exception:
        pass

    try:
        from ..integrations.weread import CredError, client_from_settings
        if client is None:
            try:
                client = client_from_settings(env=env)
            except CredError:
                return _empty_booklist_side(
                    message="书单旁证（微信读书）：无凭据（不强制）",
                    error_kind="CredError",
                )

        titles: list[str] = []
        seen: set[str] = set()

        # 1) 本周阅读排行
        try:
            base = int(datetime.strptime(as_of, "%Y-%m-%d").timestamp())
        except ValueError:
            base = 0
        detail = client.readdata_detail(mode="weekly", base_time=base or None)
        for item in detail.get("readLongest") or []:
            book = item.get("book") or {}
            album = (item.get("albumInfo") or {}).get("name")
            title = (book.get("title") or album or "").strip()
            if title and title not in seen:
                seen.add(title)
                titles.append(title)
            if len(titles) >= n:
                break

        # 2) 书架近读未读完补齐
        if len(titles) < n:
            shelf = client.shelf_sync()
            books = list(shelf.get("books") or [])
            books.sort(
                key=lambda b: int(b.get("readUpdateTime") or 0), reverse=True,
            )
            for b in books:
                if int(b.get("finishReading") or 0) == 1:
                    continue
                title = (b.get("title") or "").strip()
                if title and title not in seen:
                    seen.add(title)
                    titles.append(title)
                if len(titles) >= n:
                    break

        return {
            "checked": True,
            "enabled": True,
            "titles": titles[:n],
            "message": (
                f"书单旁证（微信读书）：{len(titles[:n])} 条（只读）"
                if titles else
                "书单旁证（微信读书）：本周暂无阅读排行 / 近读书籍"
            ),
            "error_kind": None,
        }
    except Exception as e:
        return _empty_booklist_side(
            message=f"书单旁证（微信读书）：检查失败（{type(e).__name__}，不强制）",
            error_kind=type(e).__name__,
        )


def clickup_booklist_hint(
    *,
    as_of: str,
    list_ids: tuple[str, ...] | None = None,
    max_n: int | None = None,
    recent_closed_days: int | None = None,
    client=None,
    fetch=None,
    env=None,
) -> dict:
    """ClickUp 日常事务旁证：开 / 近完成的书课任务标题。失败不抛。"""
    rules = LEARNING_WEEK_RULES or {}
    if not rules.get("clickup_enabled", True):
        return _empty_booklist_side(
            message="书单旁证（ClickUp）：已关闭", enabled=False,
        )
    n = int(max_n if max_n is not None else rules.get("booklist_max") or 10)
    recent = int(
        recent_closed_days
        if recent_closed_days is not None
        else rules.get("booklist_recent_closed_days") or 14
    )
    ids = tuple(list_ids or LEARNING_LIST_IDS or ())
    ids = tuple(x for x in ids if x)
    if not ids:
        return _empty_booklist_side(
            message="书单旁证（ClickUp）：未配置 LEARNING_LIST_IDS",
            error_kind="Config",
        )

    try:
        from ..integrations.flags import is_enabled
        if not is_enabled("clickup"):
            return _empty_booklist_side(
                message="书单旁证（ClickUp）：集成已关闭", enabled=False,
            )
    except Exception:
        pass

    try:
        from ..integrations.clickup import Client, CredError, fetch_tasks, load_creds
        from ..pipeline.clickup import completion_day
        from ..pipeline.clickup_sync import is_closed

        if client is None and fetch is None:
            try:
                key, _team = load_creds(env=env)
            except CredError:
                return _empty_booklist_side(
                    message="书单旁证（ClickUp）：无凭据（不强制）",
                    error_kind="CredError",
                )
            client = Client(key)

        try:
            as_of_d = datetime.strptime(as_of, "%Y-%m-%d").date()
        except ValueError:
            as_of_d = date.today()
        floor = (as_of_d - timedelta(days=recent)).isoformat()

        terms = _booklist_hint_terms()
        open_titles: list[str] = []
        closed_titles: list[tuple[str, str]] = []  # (closed_day, title)
        seen: set[str] = set()

        for lid in ids:
            if fetch is not None:
                tasks = fetch_tasks(lid, "", fetch=fetch)
            else:
                tasks = client.list_tasks(lid, include_closed=True)
            for t in tasks or []:
                name = (t.get("name") or "").strip()
                if not name or name in seen:
                    continue
                if not _title_matches_booklist(name, terms):
                    continue
                if not is_closed(t):
                    seen.add(name)
                    open_titles.append(name)
                    continue
                cd = completion_day(t)
                if cd and floor <= cd <= as_of_d.isoformat():
                    seen.add(name)
                    closed_titles.append((cd, name))

        closed_titles.sort(key=lambda x: x[0], reverse=True)
        titles = open_titles + [t for _, t in closed_titles]
        titles = titles[:n]
        return {
            "checked": True,
            "enabled": True,
            "titles": titles,
            "message": (
                f"书单旁证（ClickUp）：{len(titles)} 条（只读）"
                if titles else
                "书单旁证（ClickUp）：无匹配的开 / 近完成书课任务"
            ),
            "error_kind": None,
        }
    except Exception as e:
        return _empty_booklist_side(
            message=f"书单旁证（ClickUp）：检查失败（{type(e).__name__}，不强制）",
            error_kind=type(e).__name__,
        )


def booklist_evidence(
    *,
    as_of: str,
    include: bool = True,
    weread_client=None,
    clickup_client=None,
    clickup_fetch=None,
    env=None,
) -> dict:
    """双源书单旁证汇总；``include=False`` 时两侧都标关闭且不触网。"""
    if not include:
        return {
            "weread": _empty_booklist_side(
                message="书单旁证（微信读书）：本入口未拉取", enabled=False,
            ),
            "clickup": _empty_booklist_side(
                message="书单旁证（ClickUp）：本入口未拉取", enabled=False,
            ),
        }
    return {
        "weread": weread_booklist_hint(
            as_of=as_of, client=weread_client, env=env,
        ),
        "clickup": clickup_booklist_hint(
            as_of=as_of, client=clickup_client, fetch=clickup_fetch, env=env,
        ),
    }


def collect(
    conn,
    *,
    as_of: str | None = None,
    rebuild: bool = True,
    include_booklist: bool | None = None,
    weread_client=None,
    clickup_client=None,
    clickup_fetch=None,
    env=None,
) -> dict:
    """汇学习报告数据（结构化，文本 / JSON 共用）。

    ``include_booklist``：``None`` → 跟 ``LEARNING_WEEK_RULES['booklist_enabled']``；
    steward / analyze 挂接应显式传 ``False`` 避免触网。
    """
    if as_of is None:
        row = conn.execute(
            "SELECT MAX(date) FROM learning_logs"
        ).fetchone()
        as_of = row[0] if row and row[0] else date.today().isoformat()

    if rebuild:
        rebuild_review_queue(conn)
        conn.commit()

    queue_rows = [dict(r) for r in load_review_queue(conn)]
    due_today: list[dict] = []
    overdue: list[dict] = []
    pending: list[dict] = []
    for q in queue_rows:
        status = due_status(as_of, q["due_date"])
        item = {**q, "status": status}
        if status == "due":
            due_today.append(item)
        elif status == "overdue":
            overdue.append(item)
        else:
            pending.append(item)

    week_start, week_end = _iso_week_bounds(as_of)
    week_logs = [
        dict(r) for r in load_learning_logs(
            conn, start=week_start, end=week_end
        )
    ]
    week = week_rollup(week_logs)
    learn_h_rows = _load_learn_h_rows(conn, week_start, week_end)
    week = enrich_week_hours_from_logs(week, week_logs, learn_h_rows)

    rules = LEARNING_WEEK_RULES or {}
    want_books = (
        rules.get("booklist_enabled", True)
        if include_booklist is None else bool(include_booklist)
    )
    booklist = booklist_evidence(
        as_of=as_of,
        include=want_books,
        weread_client=weread_client,
        clickup_client=clickup_client,
        clickup_fetch=clickup_fetch,
        env=env,
    )
    week["booklist"] = booklist

    return {
        "as_of": as_of,
        "intervals": list(SPACED_REPEAT.get("intervals") or [1, 3, 7, 16]),
        "due_today": due_today,
        "overdue": overdue,
        "pending": pending,
        "queue_total": len(queue_rows),
        "week": {
            "start": week_start,
            "end": week_end,
            **week,
        },
        "booklist": booklist,
        "evidence_lists": list(LEARNING_LIST_IDS),
    }


def _hours_lines(week: dict) -> list[str]:
    """投入行（含 learn_h 兜底说明）。"""
    L: list[str] = []
    source = week.get("hours_source") or "none"
    logs_m = week.get("logs_minutes")
    used_h = week.get("learn_h_used_total")
    used_days = week.get("learn_h_used_days") or 0
    entries = week.get("entries", 0)
    log_days = len(week.get("days") or [])

    if source == "logs":
        total_s = f"{logs_m:.0f}min" if logs_m is not None else "—"
        L.append(
            f"  投入 {total_s}（learning_logs） · {entries} 条 · {log_days} 天"
        )
    elif source == "learn_h":
        hs = f"{used_h:g}h" if used_h is not None else "—"
        L.append(
            f"  投入 {hs}（来自日汇总 learn_h；附录学习记录为空）"
            f" · {used_days} 天"
        )
    elif source == "mixed":
        total_s = f"{logs_m:.0f}min" if logs_m is not None else "—"
        hs = f"{used_h:g}h" if used_h is not None else "—"
        L.append(
            f"  投入 {total_s}（logs）+ {hs} 空日兜底（learn_h）"
            f" · logs {entries} 条 / {log_days} 天 · 兜底 {used_days} 天"
        )
    return L


def _booklist_lines(booklist: dict | None) -> list[str]:
    if not booklist:
        return []
    L: list[str] = ["  ---- 书单旁证 ----"]
    for key, label in (("weread", "微信读书"), ("clickup", "ClickUp")):
        side = booklist.get(key) or {}
        msg = side.get("message") or f"{label}：—"
        L.append(f"  · {msg}")
        for t in side.get("titles") or []:
            L.append(f"    - {t}")
    return L


def week_section_lines(week: dict) -> list[str]:
    """给 analyze / steward 挂段用的纯文本行（不含大标题）。"""
    L: list[str] = []
    topics = week.get("topics") or []
    if not topics:
        L.append("  （本周无 learning_logs）")
    L.extend(_hours_lines(week))
    for t in topics:
        m = t.get("minutes")
        ms = f"{m:.0f}min" if m is not None else "—"
        L.append(f"  · {t['topic_key']}: {ms}（{t['entries']}）· {t['topic']}")
    arts = week.get("artifacts") or []
    if arts:
        L.append("  产出物: " + "；".join(arts[:8]))
        if len(arts) > 8:
            L.append(f"  …另有 {len(arts) - 8} 项")
    L.extend(_booklist_lines(week.get("booklist")))
    return L


def render(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 52)
    L.append("DailyLumen 学习 / 复习报告（不计入四维评分）")
    L.append("=" * 52)
    L.append(
        f"锚点日: {data['as_of']}  ·  间隔: "
        f"{'/'.join(str(i) + 'd' for i in data['intervals'])}"
        f"  ·  队列: {data['queue_total']}"
    )
    L.append("")
    L.append("---- 今日待复习 ----")
    due = data.get("due_today") or []
    overdue = data.get("overdue") or []
    if not due and not overdue:
        L.append("  （无到期 / 逾期项）")
    else:
        for it in overdue:
            L.append(
                f"  ! 逾期 {it['topic']}（{it['topic_key']}）"
                f"  due={it['due_date']} stage={it['stage']}"
                f"  last={it.get('last_seen') or '—'}"
            )
        for it in due:
            L.append(
                f"  * 到期 {it['topic']}（{it['topic_key']}）"
                f"  stage={it['stage']}"
                f"  last={it.get('last_seen') or '—'}"
            )
    L.append("")
    week = data.get("week") or {}
    L.append(
        f"---- 本周主题 / 投入 / 产出物"
        f"（{week.get('start')} ~ {week.get('end')}）----"
    )
    L.extend(week_section_lines(week))
    L.append("")
    ids = data.get("evidence_lists") or []
    if ids:
        L.append(
            "证据链（ClickUp，只读素材）: "
            + " ".join(f"--list {i}" for i in ids)
        )
        L.append("讲解 / 出题交给对话现场能力，本命令不生成题库。")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print("用法: python -m review_tool tutor [YYYY-MM-DD] [--json]")
        print("      今日待复习 + 本周主题/投入/产出物（独立指标区）")
        print("      F2：learn_h 兜底 + 微信读书/ClickUp 书单旁证（软失败）")
        print(
            f"      证据链: clickup --list {LEARNING_LIST_IDS[0]}"
            "   # v1.24.0 起并入日常事务"
        )
        return 0

    as_json = "--json" in argv
    args = [a for a in argv if not a.startswith("--")]
    as_of = args[0] if args else None

    conn = init_db()
    try:
        # CLI 默认拉旁证（LEARNING_WEEK_RULES）；失败软降级，rc 仍 0
        data = collect(conn, as_of=as_of, rebuild=True, include_booklist=None)
        if as_json:
            print(json.dumps(data, ensure_ascii=False, indent=2))
        else:
            print(render(data))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

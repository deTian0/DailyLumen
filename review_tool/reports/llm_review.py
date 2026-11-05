"""llm-review：DeepSeek 评价链路（复用 ai-context / 书口径措辞约束）。

流程：读 ``ai-review`` 同源事实与关注点 →（仅 mode=deepseek）调 DeepSeek chat →
**只写入**当日复盘 md「七、AI 评价与建议」草稿区（标注草稿/待人审）→
人审后再 ``ingest``。⛔ 不直写库；⛔ 不另造评分算法（R1）。

``workbuddy`` 模式清晰拒绝。默认 dry-run；``--write`` 落盘；
``--diff`` / dry-run 显示将写入「七、AI」的新旧差异。
"""
from __future__ import annotations

import datetime
import difflib
import os
import re
import sys
from collections.abc import Callable
from typing import Any

from ..core.ai_draft import stamp_llm_pending
from ..core.llm_mode import LLM_MODE_DEEPSEEK, LLM_MODE_WORKBUDDY, normalize_llm_mode
from ..pipeline.deepseek import (
    Client,
    DeepSeekCredError,
    DeepSeekError,
    DeepSeekModeError,
    assistant_text,
    get_llm_mode,
)
from ..pipeline.keepstrong_sync import review_md_path
from ..pipeline.llm_runlog import write_llm_last_run
from .ai_review import build_context, render_markdown

USAGE = (
    "llm-review [YYYY-MM-DD] [--write] [--dry-run] [--diff] [--stdout] "
    "[--md PATH] [--db PATH]"
)

SECTION_TITLE = "## 七、AI 评价与建议"
_SECTION_RE = re.compile(
    r"(^##\s*七、AI 评价与建议[^\n]*\n)(.*?)(?=^##\s|\Z)",
    re.S | re.M,
)

# 与 ai_review.render_markdown 撰写要求 / intake §4 / 书口径对齐；不发明评分阈值
SYSTEM_PROMPT = """你是 DailyLumen 日复盘助手。根据用户给出的「AI 评价上下文」撰写当日
「七、AI 评价与建议」正文。

硬规则（与本地 ai-context / intake §4 / life-decision-guide 书口径一致，⛔ 勿另造评分算法）：
1. 只使用上下文里出现的数字与「规则命中的关注点」；⛔ 不得编造未列出的数据。
2. 上下文里的关注点文案已由本地规则（SCORE_THRESHOLDS / 宏量目标 / 极端节食等）算好；
   评价须回应这些关注点，但不要改写阈值数字，也不要自行打「健康分/系统分」。
3. 若关注点含「极端偏低」或连续极低热量：⛔ 不要把「吃得少」算作做得好。
4. 建议段可执行、带时间锚点或目标值；涉及改进排序时注明「须人审挂 life-decision-guide」，
   你不必也不应编造书条目编号。
5. 先写「评价」2–3 条（做得好 / 需留意），再写「建议」2–4 条。
6. 输出 Markdown，结构必须是：

**评价**

- …

**建议**

1. **引领**：…
2. …

7. 不要输出章节标题「## 七、…」；不要表格；不要编造熔断状态（上下文未给则不提）。
8. 体征：体重 / 腰围 / **体脂率** 仅当上下文明确给出才可引用；
   上下文无体脂率时 ⛔ 禁止编造、估算或假设体脂（无设备缺测属合法，勿当缺口苛责）。
"""


def build_user_prompt(context_md: str, *, day: str) -> str:
    return (
        f"对象日：{day}\n\n"
        "请严格依据下列上下文撰写评价与建议"
        "（上下文含当日事实、近窗均值、规则命中的关注点；判定已由本地完成）：\n\n"
        f"{context_md.strip()}\n"
    )


def wrap_ai_draft(body: str, *, day: str, generated_at: str) -> str:
    """包一层草稿标注；body 为模型产出的评价/建议段。

    含「草稿 / 待人审」时 ``ingest`` 默认跳过本文件（见 ``core.ai_draft``）。
    """
    inner = (body or "").strip()
    lines = [
        SECTION_TITLE,
        "",
        "### 七-A · AI 草稿（待人审）",
        "",
        f"> ⚠️ **草稿 / 待人审**（DeepSeek · llm-review · {day} · {generated_at}）",
        "> 人审后写入「七-B · 定稿」或改写本段并**去掉本标记**，再 `ingest`；",
        "> 含此标记时 ingest **默认跳过**（``--allow-ai-draft`` 可强制）。⛔ 本命令不写库。",
        "",
        inner if inner else "- （模型未返回正文）",
        "",
        "### 七-B · 定稿（人审通过）",
        "",
        "> 人审通过后的评价与建议写在这里；定稿后请删除七-A 草稿标记 /",
        "> 文件头 ``<!-- dailylumen:llm-pending-review -->``。",
        "",
    ]
    return "\n".join(lines)


def extract_ai_section(md_text: str) -> str:
    """取出「七、AI…」整节（含标题）；没有则空串。"""
    text = md_text.replace("\r\n", "\n")
    m = _SECTION_RE.search(text)
    if not m:
        return ""
    return (m.group(0) or "").rstrip() + "\n"


def format_section_diff(old: str, new: str) -> str:
    """统一 diff（stdout）；无旧节时标注为新增。"""
    old_lines = (old or "").splitlines(keepends=True)
    new_lines = (new or "").splitlines(keepends=True)
    if not old_lines:
        header = "--- 七、AI（旧：无此节）\n+++ 七、AI（新草稿）\n"
        return header + "".join(
            ln if ln.startswith("+") else f"+{ln}" for ln in new_lines
        )
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="七、AI（旧）",
            tofile="七、AI（新草稿）",
            n=2,
        )
    )


def apply_ai_section(md_text: str, section_md: str) -> str:
    """幂等替换「七、AI 评价与建议」整节；没有则插在「附录」或文末前。"""
    text = md_text.replace("\r\n", "\n")
    section = section_md.strip() + "\n"
    m = _SECTION_RE.search(text)
    if m:
        return text[: m.start()] + section + text[m.end() :]
    # 插在「## 附录」前；否则文末
    am = re.search(r"^##\s*附录", text, re.M)
    if am:
        return text[: am.start()].rstrip() + "\n\n" + section + "\n" + text[am.start() :]
    return text.rstrip() + "\n\n" + section + "\n"


def _parse(argv: list[str]) -> dict[str, Any]:
    day: str | None = None
    write = False
    dry_run = False
    to_stdout = False
    show_diff = False
    md_path: str | None = None
    db_path: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--write",):
            write = True
        elif a in ("--dry-run",):
            dry_run = True
        elif a == "--diff":
            show_diff = True
        elif a == "--stdout":
            to_stdout = True
        elif a == "--md":
            i += 1
            if i >= len(argv):
                raise ValueError("--md 需要跟路径")
            md_path = argv[i]
        elif a.startswith("--md="):
            md_path = a.split("=", 1)[1]
        elif a == "--db":
            i += 1
            if i >= len(argv):
                raise ValueError("--db 需要跟路径")
            db_path = argv[i]
        elif a.startswith("--db="):
            db_path = a.split("=", 1)[1]
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            if day is None:
                day = a
            else:
                raise ValueError(f"多余的位置参数: {a}")
        i += 1
    if day is None:
        day = datetime.date.today().isoformat()
    else:
        try:
            datetime.date.fromisoformat(day)
        except ValueError:
            raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    if dry_run:
        write = False
    elif not write:
        dry_run = True
    return {
        "day": day,
        "write": write,
        "dry_run": dry_run,
        "diff": show_diff or dry_run,
        "stdout": to_stdout or dry_run,
        "md_path": md_path,
        "db_path": db_path,
    }


def run_llm_review(
    day: str,
    *,
    db_path: str | None = None,
    md_path: str | None = None,
    write: bool = False,
    client: Client | None = None,
    mode: str | None = None,
    now: Callable[[], str] | None = None,
    log_path: str | None = None,
    skip_runlog: bool = False,
) -> dict[str, Any]:
    """编排：取上下文 → DeepSeek → 组装草稿 → 可选写 md。

    ``client`` 可注入（测试 mock）；``mode`` 可覆盖 Settings。
    """
    m = normalize_llm_mode(mode) if mode is not None else get_llm_mode()

    def _log(ok: bool, **extra: Any) -> None:
        if skip_runlog:
            return
        try:
            write_llm_last_run(
                {
                    "command": "llm-review",
                    "mode": m,
                    "ok": ok,
                    "day": day,
                    **extra,
                },
                path=log_path,
            )
        except OSError:
            pass

    if m != LLM_MODE_DEEPSEEK:
        _log(False, error_kind="mode", error_summary=f"mode={m} 禁止调 DeepSeek")
        raise DeepSeekModeError(
            f"当前 DAILYLUMEN_LLM_MODE={m!r}，llm-review 仅在 "
            f"{LLM_MODE_DEEPSEEK!r} 模式下调用 DeepSeek。"
            f"\n请改走 WorkBuddy / Cursor 宿主按 skill `daily-review-intake` §4 "
            f"撰写「七、AI」，或把 local/.env 设为 "
            f"DAILYLUMEN_LLM_MODE={LLM_MODE_DEEPSEEK}。"
            f"（{LLM_MODE_WORKBUDDY!r}=宿主代劳，仓库不调外部模型）"
        )

    ctx = build_context(day, db_path=db_path)
    context_md = render_markdown(ctx)
    stamp = now() if callable(now) else datetime.datetime.now().strftime(
        "%Y-%m-%d %H:%M"
    )

    c = client or Client(mode=m)
    try:
        resp = c.chat_completions(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(context_md, day=day)},
            ],
            temperature=0.3,
            max_tokens=1200,
        )
    except (DeepSeekCredError, DeepSeekError) as e:
        _log(False, error_kind=type(e).__name__, error_summary=str(e)[:200])
        raise

    body = assistant_text(resp).strip()
    section = wrap_ai_draft(body, day=day, generated_at=stamp)

    path = md_path or review_md_path(day)
    old_section = ""
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            old_section = extract_ai_section(f.read())

    result: dict[str, Any] = {
        "day": day,
        "mode": m,
        "md_path": path,
        "section": section,
        "old_section": old_section,
        "diff_text": format_section_diff(old_section, section),
        "context_empty": ctx.get("day") is None,
        "flags": list(ctx.get("flags") or []),
        "written": False,
        "changed": False,
    }

    if not write:
        _log(
            True,
            written=False,
            changed=old_section.replace("\r\n", "\n") != section.replace("\r\n", "\n"),
        )
        return result

    if not os.path.isfile(path):
        _log(False, error_kind="file", error_summary=f"找不到复盘 md：{path}")
        raise FileNotFoundError(f"找不到复盘 md：{path}")

    with open(path, encoding="utf-8") as f:
        original = f.read()
    updated = stamp_llm_pending(apply_ai_section(original, section))
    result["changed"] = updated.replace("\r\n", "\n") != original.replace(
        "\r\n", "\n"
    )
    if result["changed"]:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(updated)
        with open(path, encoding="utf-8") as f:
            got = f.read()
        if got.replace("\r\n", "\n") != updated.replace("\r\n", "\n"):
            raise OSError(f"写盘回读不一致: {path}")
        result["written"] = True
        result["pending_review"] = True

    _log(True, written=bool(result["written"]), changed=bool(result["changed"]))
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("DeepSeek：ai-context → 写「七、AI」草稿（待人审）；默认 dry-run。")
        print("仅 DAILYLUMEN_LLM_MODE=deepseek；workbuddy 请走宿主 intake。")
        print("--diff / dry-run 显示将写入「七、AI」的新旧差异。")
        return 0
    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        result = run_llm_review(
            opts["day"],
            db_path=opts["db_path"],
            md_path=opts["md_path"],
            write=opts["write"],
        )
    except DeepSeekModeError as e:
        print(str(e), file=sys.stderr)
        return 2
    except DeepSeekCredError as e:
        print(str(e), file=sys.stderr)
        return 2
    except DeepSeekError as e:
        print(f"DeepSeek 调用失败: {e}", file=sys.stderr)
        return 1
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"写盘失败: {e}", file=sys.stderr)
        return 1

    if opts["stdout"]:
        print(result["section"])
    if opts.get("diff"):
        print("--- 七、AI 草稿差异 ---")
        print(result.get("diff_text") or "(无差异)")
    if opts["dry_run"]:
        print(
            f"[dry-run] 未写盘；目标 md: {result['md_path']}"
            f"{'（库无该日，上下文为空）' if result['context_empty'] else ''}"
        )
        print(
            "确认后加 --write；写盘带草稿/pending 标记，"
            "ingest 默认跳过至人审去掉标记。"
        )
    elif result["written"]:
        print(f"已写入「七、AI」草稿: {result['md_path']}")
        print("请人审后 ingest（本命令不写库）。")
    else:
        print(f"内容未变，跳过写盘: {result['md_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""llm-day：一键日流程（多图 vision → 可选评价草稿）。

编排 ``llm-vision`` + 可选 ``llm-review``；默认 dry-run；``--write`` **只写 md**
（数据块 ±「七、AI」草稿），⛔ 不直写库。仅 ``DAILYLUMEN_LLM_MODE=deepseek``。

体脂可选：读图缺 ``体脂率`` 属合法；评价链路禁止编造体脂。
"""
from __future__ import annotations

import datetime
import json
import sys
from collections.abc import Callable, Sequence
from typing import Any

from ..core.llm_mode import LLM_MODE_DEEPSEEK, LLM_MODE_WORKBUDDY, normalize_llm_mode
from ..pipeline.deepseek import (
    Client,
    DeepSeekCredError,
    DeepSeekError,
    DeepSeekModeError,
    get_llm_mode,
)
from ..pipeline.llm_runlog import write_llm_last_run
from ..pipeline.vision_intake import run_vision_intake
from .llm_review import run_llm_review

USAGE = (
    "llm-day --image PATH [--image PATH ...] --date YYYY-MM-DD "
    "[--kind auto|diet|sleep|screen] "
    "[--review] [--write] [--archive-inbox] [--dry-run] [--diff] "
    "[--stdout] [--md PATH] [--db PATH]"
)


def _parse(argv: list[str]) -> dict[str, Any]:
    images: list[str] = []
    day: str | None = None
    write = False
    dry_run = False
    to_stdout = False
    show_diff = False
    do_review = False
    archive_inbox = False
    md_path: str | None = None
    db_path: str | None = None
    kind = "auto"
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--image":
            i += 1
            if i >= len(argv):
                raise ValueError("--image 需要跟路径")
            images.append(argv[i])
        elif a.startswith("--image="):
            images.append(a.split("=", 1)[1])
        elif a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a == "--kind":
            i += 1
            if i >= len(argv):
                raise ValueError("--kind 需要跟 auto|diet|sleep|screen")
            kind = argv[i]
        elif a.startswith("--kind="):
            kind = a.split("=", 1)[1]
        elif a == "--write":
            write = True
        elif a == "--dry-run":
            dry_run = True
        elif a == "--diff":
            show_diff = True
        elif a == "--stdout":
            to_stdout = True
        elif a == "--review":
            do_review = True
        elif a == "--archive-inbox":
            archive_inbox = True
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
            if day is None and len(a) == 10 and a[4] == "-" and a[7] == "-":
                try:
                    datetime.date.fromisoformat(a)
                    day = a
                except ValueError:
                    images.append(a)
            else:
                images.append(a)
        i += 1
    if not images:
        raise ValueError("必须提供至少一张 --image PATH")
    if not day:
        raise ValueError("必须提供 --date YYYY-MM-DD")
    try:
        datetime.date.fromisoformat(day)
    except ValueError:
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from None
    from ..pipeline.vision_intake import normalize_vision_kind

    kind = normalize_vision_kind(kind)
    if dry_run:
        write = False
    elif not write:
        dry_run = True
    if archive_inbox and not write:
        raise ValueError("--archive-inbox 仅可与 --write 同用（dry-run 不归档）")
    return {
        "images": images,
        "day": day,
        "write": write,
        "dry_run": dry_run,
        "diff": show_diff or dry_run or write,
        "stdout": to_stdout or dry_run,
        "review": do_review,
        "archive_inbox": archive_inbox,
        "md_path": md_path,
        "db_path": db_path,
        "kind": kind,
    }


def run_llm_day(
    image_path: str | Sequence[str],
    day: str,
    *,
    md_path: str | None = None,
    db_path: str | None = None,
    write: bool = False,
    review: bool = False,
    archive_inbox: bool = False,
    client: Client | None = None,
    mode: str | None = None,
    image_loader: Callable[[str], str] | None = None,
    log_path: str | None = None,
    skip_runlog: bool = False,
    now: Callable[[], str] | None = None,
    inbox_dir: str | None = None,
    kind: str = "auto",
) -> dict[str, Any]:
    """多图 vision →（可选）llm-review；默认不写盘。"""
    m = normalize_llm_mode(mode) if mode is not None else get_llm_mode()

    def _log(ok: bool, **extra: Any) -> None:
        if skip_runlog:
            return
        try:
            write_llm_last_run(
                {
                    "command": "llm-day",
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
            f"当前 DAILYLUMEN_LLM_MODE={m!r}，llm-day 仅在 "
            f"{LLM_MODE_DEEPSEEK!r} 模式下可用。"
            f"\nworkbuddy 请由宿主按 skill `daily-review-intake` 履约落 md"
            f"（或设 DAILYLUMEN_LLM_MODE={LLM_MODE_DEEPSEEK}）；"
            f"{LLM_MODE_WORKBUDDY!r}=宿主代劳。"
        )

    c = client or Client(mode=m)
    vision = run_vision_intake(
        image_path,
        day,
        md_path=md_path,
        write=write,
        client=c,
        mode=m,
        image_loader=image_loader,
        log_path=log_path,
        skip_runlog=True,  # 由本命令统一写 runlog
        kind=kind,
    )

    review_result: dict[str, Any] | None = None
    if review:
        review_result = run_llm_review(
            day,
            db_path=db_path,
            md_path=md_path or vision.get("md_path"),
            write=write,
            client=c,
            mode=m,
            now=now,
            log_path=log_path,
            skip_runlog=True,
        )

    written = bool(vision.get("written")) or bool(
        (review_result or {}).get("written")
    )
    archive_result: dict[str, Any] | None = None
    if archive_inbox and write and written:
        from ..pipeline.inbox_archive import archive_inbox_files

        imgs = list(vision.get("images") or [])
        if not imgs:
            if isinstance(image_path, (str, bytes)):
                imgs = [str(image_path)]
            else:
                imgs = [str(p) for p in image_path]
        archive_result = archive_inbox_files(
            imgs, day, inbox_dir=inbox_dir, write=True
        )

    classification = vision.get("classification") or {}
    result: dict[str, Any] = {
        "day": day,
        "mode": m,
        "kind": vision.get("kind") or kind,
        "vision": vision,
        "review": review_result,
        "md_path": vision.get("md_path"),
        "fields": vision.get("fields") or {},
        "conflicts": vision.get("conflicts") or [],
        "failed_images": vision.get("failed_images") or [],
        "written": written,
        "archive": archive_result,
    }

    _log(
        True,
        written=bool(result["written"]),
        review=bool(review),
        kind=result["kind"],
        archived=len((archive_result or {}).get("moved") or []),
        image_count=len(vision.get("images") or []),
        filled_fields=classification.get("filled"),
        missing_fields=(classification.get("missing") or [])[:20],
        optional_missing=(classification.get("optional_missing") or [])[:10],
        conflict_count=len(result["conflicts"]),
        failed_image_count=len(result["failed_images"]),
    )
    return result


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("一键日流程：多图 llm-vision →（可选 --review）llm-review 草稿。")
        print("默认 dry-run；--write 只写 md（数据块 ±「七、AI」）；⛔ 不直写库。")
        print("--kind auto|diet|sleep|screen：分模板读图，减少串字段。")
        print("--archive-inbox：写盘成功后把本次 --image 移到 收件箱/已处理/日/。")
        print("仅 mode=deepseek。体脂率可选，无读数勿伪造。")
        print("结束输出收工摘要（读到/空缺/下一条）。")
        return 0
    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        result = run_llm_day(
            opts["images"],
            opts["day"],
            md_path=opts["md_path"],
            db_path=opts["db_path"],
            write=opts["write"],
            review=opts["review"],
            archive_inbox=opts["archive_inbox"],
            kind=opts["kind"],
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
    except ValueError as e:
        print(f"契约解析失败: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"写盘失败: {e}", file=sys.stderr)
        return 1

    vision = result["vision"]
    filled = (vision.get("classification") or {}).get("filled") or []
    opt_miss = (vision.get("classification") or {}).get("optional_missing") or []
    conflicts = result.get("conflicts") or []
    failed = result.get("failed_images") or []

    if opts["stdout"]:
        print(json.dumps(result["fields"], ensure_ascii=False, indent=2))
        if opts["review"] and result.get("review"):
            print("--- 七、AI 草稿预览 ---")
            print((result["review"] or {}).get("section") or "")

    if conflicts:
        print("--- 多图字段冲突（后图覆盖）---")
        for c in conflicts:
            print(f"  {c['key']}: {c['was']} → {c['now']} ({c['strategy']})")
    if failed:
        print("--- 读图失败文件（已跳过）---")
        for f in failed:
            print(f"  {f['path']}: {f['error']}")

    if opts.get("diff"):
        print("=== 定稿前并排预览：数据块 +「七、AI」 ===")
        diff_lines = vision.get("diff_lines") or []
        if diff_lines:
            print("--- 数据块 ---")
            for ln in diff_lines:
                print(ln)
        else:
            print("--- 数据块：无明显契约字段变更 ---")
        if opts["review"] and result.get("review"):
            print("--- 七、AI ---")
            print((result["review"] or {}).get("diff_text") or "(无差异)")
        elif opts["review"]:
            print("--- 七、AI：（无草稿产出）---")
        else:
            print("--- 七、AI：（未加 --review，跳过）---")

    if opts["dry_run"]:
        print(
            f"[dry-run] 未写盘；目标 md: {result['md_path']}；"
            f"kind={result.get('kind') or opts.get('kind')}；"
            f"已识别 {len(filled)} 项"
            + ("；含 --review" if opts["review"] else "")
        )
        if filled:
            print("  将写入: " + ", ".join(filled))
        if "体脂率" in opt_miss:
            print("  体脂率：未识别（可选；无设备可跳过，勿伪造）")
        print(
            "确认后加 --write；写盘会戳 pending/草稿标记，"
            "ingest 默认跳过至人审去掉标记。"
        )
    elif result["written"]:
        bits = []
        if vision.get("written"):
            bits.append("数据块")
        if (result.get("review") or {}).get("written"):
            bits.append("七、AI 草稿")
        print(f"已写入 ({'+'.join(bits) or '无变更'}): {result['md_path']}")
        print(
            "请人审：python -m review_tool llm-finalize <日> --write；"
            "再 ingest（本命令不写库）。"
        )
        arch = result.get("archive") or {}
        if arch.get("moved"):
            print(
                f"已归档 {len(arch['moved'])} 张 → {arch.get('dest_dir')}"
            )
        elif opts.get("archive_inbox") and arch is not None:
            n_skip = len(arch.get("skipped") or [])
            print(f"归档：无可移动文件（跳过 {n_skip}）")
    else:
        print(f"无新内容可写或内容未变: {result['md_path']}")

    from .day_close import close_summary_for_llm_day

    print("[收工摘要]")
    print(close_summary_for_llm_day(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

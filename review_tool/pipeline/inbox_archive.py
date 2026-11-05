"""收件箱归档：成功处理后的图片 → ``收件箱/已处理/YYYY-MM-DD/``。

优先**移动**（比删除安全）；可还原。默认 dry-run；``--write`` 才落盘。
独立 CLI ``inbox-archive``；亦可挂在 ``llm-day --write --archive-inbox``。
"""
from __future__ import annotations

import datetime
import os
import shutil
import sys
from collections.abc import Sequence
from typing import Any

from ..config import INBOX_DIR

USAGE = (
    "inbox-archive --date YYYY-MM-DD --file PATH [--file PATH ...] "
    "[--write] [--dry-run] [--inbox DIR]"
)

PROCESSED_DIRNAME = "已处理"

# 默认只归档常见截图；md 素材默认不动（除非显式传入）
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}


def processed_dir(day: str, *, inbox_dir: str | None = None) -> str:
    base = inbox_dir if inbox_dir is not None else INBOX_DIR
    return os.path.join(base, PROCESSED_DIRNAME, day)


def _same_tree(path: str, root: str) -> bool:
    try:
        return os.path.commonpath(
            [os.path.abspath(path), os.path.abspath(root)]
        ) == os.path.abspath(root)
    except ValueError:
        return False


def archive_inbox_files(
    paths: Sequence[str],
    day: str,
    *,
    inbox_dir: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    """把 ``paths`` 移到 ``收件箱/已处理/<day>/``（仅允许 inbox 树内文件）。

    返回 ``moved`` / ``skipped`` / ``planned`` 列表；``write=False`` 只规划。
    """
    try:
        datetime.date.fromisoformat(day)
    except ValueError as e:
        raise ValueError(f"日期格式应为 YYYY-MM-DD，收到: {day}") from e

    inbox = os.path.abspath(inbox_dir if inbox_dir is not None else INBOX_DIR)
    dest_root = processed_dir(day, inbox_dir=inbox)
    planned: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    moved: list[dict[str, str]] = []

    for raw in paths:
        src = os.path.abspath(raw)
        if not os.path.isfile(src):
            skipped.append({"path": src, "reason": "not_a_file"})
            continue
        if not _same_tree(src, inbox):
            skipped.append({"path": src, "reason": "outside_inbox"})
            continue
        # 已在已处理/ 下则跳过
        if _same_tree(src, os.path.join(inbox, PROCESSED_DIRNAME)):
            skipped.append({"path": src, "reason": "already_archived"})
            continue
        name = os.path.basename(src)
        dest = os.path.join(dest_root, name)
        if os.path.exists(dest):
            stem, ext = os.path.splitext(name)
            n = 2
            while os.path.exists(dest):
                dest = os.path.join(dest_root, f"{stem}__{n}{ext}")
                n += 1
        item = {"src": src, "dest": dest}
        planned.append(item)
        if write:
            os.makedirs(dest_root, exist_ok=True)
            shutil.move(src, dest)
            if not os.path.isfile(dest) or os.path.isfile(src):
                raise OSError(f"归档移动失败: {src} → {dest}")
            moved.append(item)

    return {
        "day": day,
        "inbox_dir": inbox,
        "dest_dir": dest_root,
        "write": write,
        "planned": planned,
        "moved": moved if write else [],
        "skipped": skipped,
    }


def _parse(argv: list[str]) -> dict[str, Any]:
    day: str | None = None
    files: list[str] = []
    write = False
    dry_run = False
    inbox: str | None = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--date":
            i += 1
            if i >= len(argv):
                raise ValueError("--date 需要跟日期")
            day = argv[i]
        elif a.startswith("--date="):
            day = a.split("=", 1)[1]
        elif a == "--file":
            i += 1
            if i >= len(argv):
                raise ValueError("--file 需要跟路径")
            files.append(argv[i])
        elif a.startswith("--file="):
            files.append(a.split("=", 1)[1])
        elif a == "--inbox":
            i += 1
            if i >= len(argv):
                raise ValueError("--inbox 需要跟路径")
            inbox = argv[i]
        elif a.startswith("--inbox="):
            inbox = a.split("=", 1)[1]
        elif a == "--write":
            write = True
        elif a == "--dry-run":
            dry_run = True
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            # 裸路径当文件；裸日期当 day
            if (
                day is None
                and len(a) == 10
                and a[4] == "-"
                and a[7] == "-"
            ):
                try:
                    datetime.date.fromisoformat(a)
                    day = a
                except ValueError:
                    files.append(a)
            else:
                files.append(a)
        i += 1
    if not day:
        raise ValueError("必须提供 --date YYYY-MM-DD")
    if not files:
        raise ValueError("必须提供至少一个 --file PATH")
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
        "files": files,
        "write": write,
        "dry_run": dry_run,
        "inbox": inbox,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print(
            f"将收件箱内已处理文件移到 ``收件箱/{PROCESSED_DIRNAME}/YYYY-MM-DD/``。"
        )
        print("默认 dry-run；--write 才移动。优先移动、勿误删。")
        return 0
    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        result = archive_inbox_files(
            opts["files"],
            opts["day"],
            inbox_dir=opts["inbox"],
            write=opts["write"],
        )
    except OSError as e:
        print(f"归档失败: {e}", file=sys.stderr)
        return 1

    for s in result["skipped"]:
        print(f"跳过: {s['path']} ({s['reason']})")
    items = result["moved"] if opts["write"] else result["planned"]
    for it in items:
        verb = "已移" if opts["write"] else "将移"
        print(f"{verb}: {it['src']} → {it['dest']}")
    if opts["dry_run"]:
        print(
            f"[dry-run] 未移动；计划 {len(result['planned'])} 个 → "
            f"{result['dest_dir']}"
        )
        print("确认后加 --write。")
    else:
        print(
            f"已归档 {len(result['moved'])} 个 → {result['dest_dir']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

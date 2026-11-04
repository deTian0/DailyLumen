"""llm-vision：DeepSeek 读图 → 契约字段 → 写入当日 md 数据块。

输入：一张或多张图片 + 日期 → Vision → ``llm_contract`` 归一合并 → **只写**复盘 md
的 ```data``` 契约字段（缺字段留空合法）。⛔ 不直写库；人审后 ``ingest``。

仅 ``DAILYLUMEN_LLM_MODE=deepseek``；``workbuddy`` 拒绝并提示宿主读图。
默认 dry-run；``--write`` 落盘；``--diff`` 预览数据块将变更行。
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from collections.abc import Callable, Sequence
from typing import Any

from ..config import WEEKDAY_CN
from ..core.llm_contract import (
    CONTRACT_DATA_FIELDS,
    classify_contract_fields,
    merge_contract_field_dicts,
    merge_data_block_fields,
    parse_model_structured,
)
from ..core.llm_mode import LLM_MODE_DEEPSEEK, LLM_MODE_WORKBUDDY, normalize_llm_mode
from .deepseek import (
    Client,
    DeepSeekCredError,
    DeepSeekError,
    DeepSeekModeError,
    assistant_text,
    get_llm_mode,
    image_file_to_data_url,
)
from .keepstrong_sync import review_md_path
from .llm_runlog import write_llm_last_run

USAGE = (
    "llm-vision --image PATH [--image PATH ...] --date YYYY-MM-DD "
    "[--write] [--dry-run] [--diff] [--stdout] [--md PATH]"
)

VISION_SYSTEM = (
    "你是 DailyLumen 读图助手。从截图抽取客观数字，只输出一个 JSON object。"
    "键优先用下列中文契约名（没有的键省略，⛔ 不要估算凑数）："
    + "、".join(CONTRACT_DATA_FIELDS)
    + "。也可用英文别名 diet_kcal / carbs_g / fat_g / protein_g / weight_kg 等。"
    "看不清的字段不要写。不要其它说明文字。"
)

VISION_USER_ONE = (
    "请阅读这张复盘相关截图（饮食/体脂/睡眠/屏幕等），"
    "抽出能辨认的数值，输出 JSON object；看不清的字段不要写。"
)

VISION_USER_MULTI = (
    "下面有多张复盘相关截图（可能是多餐饮食 / 睡眠 / 体脂 / 屏幕等）。"
    "合并所有能辨认的数值，输出**一个** JSON object；"
    "同一字段以最清晰可读的值为准；看不清的不要写、不要估算。"
)

_DATA_BLOCK_RE = re.compile(r"(```data\s*\n)(.*?)(```)", re.S)


def _normalize_images(image_path: str | Sequence[str]) -> list[str]:
    if isinstance(image_path, str):
        paths = [image_path]
    else:
        paths = [str(p) for p in image_path]
    if not paths:
        raise ValueError("至少提供一张 --image")
    return paths


def extract_data_block_body(md_text: str) -> str:
    """取出 ```data``` 块正文；无则空串。"""
    m = _DATA_BLOCK_RE.search(md_text.replace("\r\n", "\n"))
    return m.group(2) if m else ""


def data_block_diff_lines(before_body: str, after_body: str) -> list[str]:
    """简单行级差异：列出将变化 / 新增的契约相关行（stdout 友好）。"""
    b_lines = {ln.strip() for ln in before_body.splitlines() if ln.strip()}
    a_lines = [ln for ln in after_body.splitlines() if ln.strip()]
    out: list[str] = []
    for ln in a_lines:
        s = ln.strip()
        if s not in b_lines and any(s.startswith(k) for k in CONTRACT_DATA_FIELDS):
            out.append(f"+ {s}")
        elif s not in b_lines:
            # 日期/星期等
            if s.startswith(("日期", "星期")):
                continue
            if ":" in s or "：" in s:
                out.append(f"+ {s}")
    # 被改值：同 key 不同值
    b_map: dict[str, str] = {}
    for ln in before_body.splitlines():
        for key in CONTRACT_DATA_FIELDS:
            if ln.strip().startswith(key):
                b_map[key] = ln.strip()
    for ln in after_body.splitlines():
        for key in CONTRACT_DATA_FIELDS:
            s = ln.strip()
            if s.startswith(key) and key in b_map and b_map[key] != s:
                if f"+ {s}" not in out:
                    out.append(f"~ {b_map[key]}  →  {s}")
    return out


def run_vision_intake(
    image_path: str | Sequence[str],
    day: str,
    *,
    md_path: str | None = None,
    write: bool = False,
    client: Client | None = None,
    mode: str | None = None,
    image_loader: Callable[[str], str] | None = None,
    log_path: str | None = None,
    skip_runlog: bool = False,
) -> dict[str, Any]:
    """图片（可多张）→ Vision → 契约字段合并 → 可选写入 md 数据块。"""
    m = normalize_llm_mode(mode) if mode is not None else get_llm_mode()
    images = _normalize_images(image_path)

    def _fail_log(ok: bool, **extra: Any) -> None:
        if skip_runlog:
            return
        try:
            write_llm_last_run(
                {
                    "command": "llm-vision",
                    "mode": m,
                    "ok": ok,
                    "day": day,
                    "image_count": len(images),
                    **extra,
                },
                path=log_path,
            )
        except OSError:
            pass

    if m != LLM_MODE_DEEPSEEK:
        _fail_log(
            False,
            error_kind="mode",
            error_summary=f"mode={m} 禁止调 DeepSeek",
        )
        raise DeepSeekModeError(
            f"当前 DAILYLUMEN_LLM_MODE={m!r}，llm-vision 仅在 "
            f"{LLM_MODE_DEEPSEEK!r} 模式下调用读图 API。"
            f"\nworkbuddy 模式请由宿主按 skill `daily-review-intake` §3.5–3.6 "
            f"读图后手写/代写 md 数据块，再 ingest。"
            f"（或设 DAILYLUMEN_LLM_MODE={LLM_MODE_DEEPSEEK}）"
            f"；{LLM_MODE_WORKBUDDY!r}=宿主代劳，仓库不调外部模型。"
        )

    for p in images:
        if not os.path.isfile(p):
            _fail_log(False, error_kind="file", error_summary=f"找不到图片: {p}")
            raise FileNotFoundError(f"找不到图片: {p}")

    loader = image_loader or image_file_to_data_url
    data_urls = [loader(p) for p in images]
    c = client or Client(mode=m)
    user_text = VISION_USER_ONE if len(data_urls) == 1 else VISION_USER_MULTI

    try:
        # 多图：优先一次请求带齐；失败则逐张再合并（部分成功仍可用）
        try:
            resp = c.vision_completions(
                user_text,
                data_urls if len(data_urls) > 1 else data_urls[0],
                system=VISION_SYSTEM,
                temperature=0,
                max_tokens=768,
            )
            text = assistant_text(resp)
            fields, classification = parse_model_structured(text)
        except (DeepSeekError, ValueError):
            if len(data_urls) <= 1:
                raise
            parts: list[dict[str, Any]] = []
            last_text = ""
            for url in data_urls:
                resp = c.vision_completions(
                    VISION_USER_ONE,
                    url,
                    system=VISION_SYSTEM,
                    temperature=0,
                    max_tokens=512,
                )
                last_text = assistant_text(resp)
                f, _ = parse_model_structured(last_text)
                parts.append(f)
            fields = merge_contract_field_dicts(*parts)
            classification = classify_contract_fields(fields)
            text = last_text
    except (DeepSeekCredError, DeepSeekModeError, DeepSeekError) as e:
        _fail_log(
            False,
            error_kind=type(e).__name__,
            error_summary=str(e)[:200],
        )
        raise
    except ValueError as e:
        _fail_log(False, error_kind="parse", error_summary=str(e)[:200])
        raise

    clean = {k: v for k, v in fields.items() if k != "_unknown"}
    path = md_path or review_md_path(day)
    try:
        wd = "星期" + WEEKDAY_CN[datetime.date.fromisoformat(day).weekday()]
    except ValueError:
        wd = ""

    result: dict[str, Any] = {
        "day": day,
        "weekday": wd,
        "mode": m,
        "images": list(images),
        "image": images[0],
        "md_path": path,
        "fields": clean,
        "classification": classification,
        "raw_text": text,
        "written": False,
        "changed": False,
        "before_block": "",
        "after_block": "",
        "diff_lines": [],
    }

    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            original = f.read()
        result["before_block"] = extract_data_block_body(original)
        preview = merge_data_block_fields(original, clean)
        result["after_block"] = extract_data_block_body(preview)
        result["diff_lines"] = data_block_diff_lines(
            result["before_block"], result["after_block"]
        )
        result["changed"] = preview.replace("\r\n", "\n") != original.replace(
            "\r\n", "\n"
        )

    if not write:
        _fail_log(
            True,
            written=False,
            changed=bool(result["changed"]),
            filled_fields=classification["filled"],
            missing_fields=classification["missing"][:20],
        )
        return result

    if not os.path.isfile(path):
        _fail_log(False, error_kind="file", error_summary=f"找不到复盘 md：{path}")
        raise FileNotFoundError(f"找不到复盘 md：{path}")

    with open(path, encoding="utf-8") as f:
        original = f.read()
    updated = merge_data_block_fields(original, clean)
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
        result["before_block"] = extract_data_block_body(original)
        result["after_block"] = extract_data_block_body(updated)
        result["diff_lines"] = data_block_diff_lines(
            result["before_block"], result["after_block"]
        )

    _fail_log(
        True,
        written=bool(result["written"]),
        changed=bool(result["changed"]),
        filled_fields=classification["filled"],
        missing_fields=classification["missing"][:20],
    )
    return result


def _parse(argv: list[str]) -> dict[str, Any]:
    images: list[str] = []
    day: str | None = None
    write = False
    dry_run = False
    to_stdout = False
    show_diff = False
    md_path: str | None = None
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
        elif a == "--write":
            write = True
        elif a == "--dry-run":
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
        elif a.startswith("-"):
            raise ValueError(f"未知参数: {a}")
        else:
            # 兼容：位置参数 image… date（末位为日期）
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
    if dry_run:
        write = False
    elif not write:
        dry_run = True
    return {
        "images": images,
        "day": day,
        "write": write,
        "dry_run": dry_run,
        "diff": show_diff or dry_run,
        "stdout": to_stdout or dry_run,
        "md_path": md_path,
    }


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if any(a in ("-h", "--help") for a in argv):
        print(f"用法: python -m review_tool {USAGE}")
        print("DeepSeek Vision：截图（可多张）→ 契约字段合并 → 写当日 md 数据块；默认 dry-run。")
        print("仅 mode=deepseek；workbuddy 走宿主读图。⛔ 不直写库。")
        print("可选 --diff 预览数据块变更行；--write 前建议先 dry-run。")
        return 0
    try:
        opts = _parse(argv)
    except ValueError as e:
        print(f"参数错误: {e}", file=sys.stderr)
        print(f"用法: python -m review_tool {USAGE}", file=sys.stderr)
        return 2

    try:
        result = run_vision_intake(
            opts["images"],
            opts["day"],
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
    except ValueError as e:
        print(f"契约解析失败: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"写盘失败: {e}", file=sys.stderr)
        return 1

    filled = result["classification"]["filled"]
    missing = result["classification"]["missing"]
    n_img = len(result.get("images") or [result.get("image")])
    if opts["stdout"]:
        print(json.dumps(result["fields"], ensure_ascii=False, indent=2))
        print(f"# images={n_img} filled={len(filled)} missing={len(missing)}")
    if opts.get("diff") and result.get("diff_lines"):
        print("--- 数据块将写入差异 ---")
        for ln in result["diff_lines"]:
            print(ln)
    elif opts.get("diff") and not result.get("diff_lines"):
        print("--- 数据块无明显契约字段变更 ---")
    if opts["dry_run"]:
        print(
            f"[dry-run] 未写盘；目标 md: {result['md_path']}；"
            f"{n_img} 张图；已识别 {len(filled)} 项"
        )
        if filled:
            print("  将写入: " + ", ".join(filled))
        print("确认后加 --write；人审后再 ingest。")
    elif result["written"]:
        print(f"已写入数据块字段 ({len(filled)}): {result['md_path']}")
        print("请人审后 ingest（本命令不写库）。")
    else:
        print(f"无新字段可写或内容未变: {result['md_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""读图日流程（FR-I2 / W11）：上传或收件箱图 → vision 预览 → 写 md 数据块（不写库）；收件箱归档 / 缩略图。"""
from __future__ import annotations

import datetime
import os
from typing import Any

from ..queries import QueryError, _check_date
from .base import TokenStore, plan_out, quote_arg, register, sha_file
from .review_md import check_unchanged, ingest_cli, md_path

MAX_IMAGES = 6
MAX_IMAGE_BYTES = 8 * 1024 * 1024
_IMAGE_MAGIC = ((b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"))
_VISION_KINDS = ("auto", "diet", "sleep", "screen")
_MEDIA = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}


def _sniff_ext(raw: bytes) -> str | None:
    """按文件头判类型（不信扩展名 / 客户端 MIME）：仅 PNG / JPEG / WebP。"""
    for magic, ext in _IMAGE_MAGIC:
        if raw.startswith(magic):
            return ext
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def _decode_upload(item: dict[str, Any]) -> bytes:
    import base64
    import binascii

    data = str(item.get("data") or "")
    if "," in data and data.startswith("data:"):
        data = data.split(",", 1)[1]
    if len(data) > MAX_IMAGE_BYTES * 4 // 3 + 16:
        raise QueryError(413, "image_too_large", f"单张图片不得超过 {MAX_IMAGE_BYTES // 1024 // 1024} MB")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as e:
        raise QueryError(422, "invalid_image", "图片数据不是合法的 base64") from e
    if len(raw) > MAX_IMAGE_BYTES:
        raise QueryError(413, "image_too_large", f"单张图片不得超过 {MAX_IMAGE_BYTES // 1024 // 1024} MB")
    if not raw or _sniff_ext(raw) is None:
        raise QueryError(415, "invalid_image", "只支持 PNG / JPEG / WebP 截图")
    return raw


def _inbox_file(name: str) -> str:
    """收件箱顶层图片：只收文件名（拒绝分隔符 / ..），并再用 realpath 兜底。"""
    from ...config import INBOX_DIR

    n = (name or "").strip()
    if not n or n != os.path.basename(n) or n in (".", "..") or "/" in n or "\\" in n:
        raise QueryError(422, "path_forbidden", "收件箱文件只能传文件名")
    root = os.path.realpath(INBOX_DIR)
    p = os.path.realpath(os.path.join(root, n))
    if os.path.dirname(p) != root:
        raise QueryError(422, "path_forbidden", "只允许 收件箱/ 顶层文件")
    if not os.path.isfile(p):
        raise QueryError(404, "inbox_missing", f"收件箱里找不到 {n}")
    if os.path.getsize(p) > MAX_IMAGE_BYTES:
        raise QueryError(413, "image_too_large", f"{n} 超过 {MAX_IMAGE_BYTES // 1024 // 1024} MB")
    with open(p, "rb") as f:
        if _sniff_ext(f.read(16)) is None:
            raise QueryError(415, "invalid_image", f"{n} 不是 PNG / JPEG / WebP")
    return p


def inbox_image(name: str) -> tuple[str, str]:
    """W12 缩略图：复用 ``_inbox_file`` 的防穿越 + 大小 + magic 校验；media type 按文件头定。"""
    p = _inbox_file(name)
    with open(p, "rb") as f:
        ext = _sniff_ext(f.read(16))
    return p, _MEDIA[ext or ".png"]


def list_inbox() -> dict[str, Any]:
    """收件箱顶层图片清单（只读；``已处理/`` 不列）。"""
    from ...config import INBOX_DIR

    items = []
    if os.path.isdir(INBOX_DIR):
        for n in sorted(os.listdir(INBOX_DIR)):
            p = os.path.join(INBOX_DIR, n)
            if os.path.isfile(p) and os.path.splitext(n)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
                st = os.stat(p)
                items.append({"name": n, "size": st.st_size,
                              "mtime": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="minutes")})
    return {"items": items}


def plan_vision(tokens: TokenStore, day: str, *, kind: str = "auto",
                uploads: list[dict[str, Any]] | None = None, inbox: list[str] | None = None,
                client=None, mode: str | None = None) -> dict[str, Any]:
    """= ``llm-vision --image ... --date DAY``（dry-run）：读图 → 字段 + 冲突 + 数据块差异。

    上传图写到临时目录，**预览结束即删除**（无论成败）；token 里只存字段，不存图片。
    """
    import shutil
    import tempfile

    from ...pipeline.deepseek import DeepSeekCredError, DeepSeekError, DeepSeekModeError
    from ...pipeline.vision_intake import run_vision_intake
    from ..ai_queries import _GATE_MSG, ai_status

    day = _check_date(day)
    if kind not in _VISION_KINDS:
        raise QueryError(422, "invalid_param", "kind 只能是 auto / diet / sleep / screen")
    st = ai_status()
    eff_mode = mode or st["mode"]
    if eff_mode != "deepseek":  # 门禁在任何 I/O 之前：不落临时文件、不触网
        raise QueryError(409, "mode_gated", _GATE_MSG)
    if mode is None and not st["allowed"]:
        raise QueryError(409, "ai_disabled", st["reason"] or "AI 未开启")
    uploads, inbox = list(uploads or []), list(inbox or [])
    if not uploads and not inbox:
        raise QueryError(422, "invalid_param", "至少上传一张截图或选一张收件箱图片")
    if len(uploads) + len(inbox) > MAX_IMAGES:
        raise QueryError(422, "too_many_images", f"一次最多 {MAX_IMAGES} 张")
    inbox_paths = [_inbox_file(n) for n in inbox]
    decoded = [_decode_upload(u) for u in uploads]  # 先全部校验，再落临时文件
    md = md_path(day)

    tmp = tempfile.mkdtemp(prefix="dl-vision-")
    try:
        paths, labels = [], []
        for i, raw in enumerate(decoded):
            p = os.path.join(tmp, f"up{i + 1}{_sniff_ext(raw)}")
            with open(p, "wb") as f:
                f.write(raw)
            paths.append(p)
            labels.append(str(uploads[i].get("name") or f"上传图 {i + 1}")[:80])
        paths += inbox_paths
        labels += [os.path.basename(p) for p in inbox_paths]
        label_of = dict(zip(paths, labels, strict=True))
        try:
            res = run_vision_intake(paths, day, md_path=md, write=False, client=client,
                                    mode=eff_mode, skip_runlog=True, kind=kind)
        except DeepSeekModeError as e:
            raise QueryError(409, "mode_gated", _GATE_MSG) from e
        except DeepSeekCredError as e:
            raise QueryError(503, "ai_cred", "DeepSeek 凭据缺失或失效，请检查 local/.env") from e
        except (DeepSeekError, OSError) as e:
            raise QueryError(502, "ai_upstream", "读图调用失败（限流 / 网络 / 上游错误），请稍后重试") from e
        except ValueError as e:
            raise QueryError(502, "ai_parse", "模型返回无法解析为字段，请换图或重试") from e
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # 临时文件用后即清（成功 / 失败都清）

    fields = res["fields"]
    preview = {
        "date": day, "kind": res["kind"], "fields": fields,
        "classification": res["classification"],
        "conflicts": res["conflicts"], "merge_strategy": res.get("merge_strategy"),
        "failed_images": [{"image": label_of.get(x["path"], "?"), "error": x["error"]}
                          for x in res["failed_images"]],
        "ok_images": [label_of.get(p, "?") for p in res.get("ok_images") or []],
        "changed": res["changed"], "diff_lines": res["diff_lines"],
        "inbox": [os.path.basename(p) for p in inbox_paths],
    }
    imgs = " ".join(f"--image {quote_arg(lb)}" for lb in labels)
    return plan_out(tokens, "vision", {"date": day, "md": md, "md_sha": sha_file(md),
                                       "fields": fields},
                    preview=preview,
                    cli=f"python -m review_tool llm-vision {imgs} --date {day} --kind {kind} --write")


@register("vision")
def _apply_vision(p: dict[str, Any]) -> dict[str, Any]:
    from ...pipeline.vision_intake import write_data_block_fields

    check_unchanged(p)
    w = write_data_block_fields(p["md"], p["fields"])  # 自带写后回读；只动 md
    return {"written": w["written"], "diff_lines": w["diff_lines"], "pending_review": True,
            "next": f"数据块已写入 md（带待人审标记）；人审定稿后再入库：{ingest_cli(p['date'])}"}


def plan_inbox_archive(tokens: TokenStore, day: str, files: list[str]) -> dict[str, Any]:
    """= ``inbox-archive --date DAY --file ...``（dry-run）：移到 收件箱/已处理/DAY/。"""
    from ...config import INBOX_DIR
    from ...pipeline.inbox_archive import archive_inbox_files

    day = _check_date(day)
    if not files or len(files) > 50:
        raise QueryError(422, "invalid_param", "请给 1–50 个要归档的文件")
    paths = [_inbox_file(n) for n in files]
    inbox = os.path.realpath(INBOX_DIR)  # 与 _inbox_file 同一根，避免两处常量不同步
    res = archive_inbox_files(paths, day, inbox_dir=inbox, write=False)
    preview = {"date": day, "dest": os.path.relpath(res["dest_dir"], os.path.dirname(res["inbox_dir"])),
               "planned": [{"src": os.path.basename(x["src"]), "dest": os.path.basename(x["dest"])}
                           for x in res["planned"]],
               "skipped": [{"file": os.path.basename(x["path"]), "reason": x["reason"]}
                           for x in res["skipped"]]}
    args = " ".join(f"--file {quote_arg(p)}" for p in paths)
    return plan_out(tokens, "inbox_archive", {"date": day, "paths": paths, "inbox": inbox},
                    preview=preview,
                    cli=f"python -m review_tool inbox-archive --date {day} {args} --write")


@register("inbox_archive")
def _apply_inbox_archive(p: dict[str, Any]) -> dict[str, Any]:
    from ...pipeline.inbox_archive import archive_inbox_files

    res = archive_inbox_files(p["paths"], p["date"], inbox_dir=p["inbox"],
                              write=True)  # 移动后自校验 dest 在 / src 不在
    if not res["moved"] and p["paths"]:
        raise QueryError(409, "stale_plan", "收件箱文件在预览后已被移走或改动，请重新预览")
    return {"written": len(res["moved"]), "moved": [os.path.basename(x["dest"]) for x in res["moved"]],
            "skipped": [os.path.basename(x["path"]) for x in res["skipped"]]}

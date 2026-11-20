"""本地镜像子命令：把 ``local/`` 下 git 未追踪文件镜像到外部笔记库（Obsidian）。

    python -m review_tool mirror                 # dry-run：只看计划，不写
    python -m review_tool mirror --apply         # 真正执行（复制 + 同步删除）
    python -m review_tool mirror --target DIR    # 覆盖配置里的目标目录
    python -m review_tool mirror --src DIR       # 覆盖源目录（默认 local/；测试/换机用）
    python -m review_tool mirror --no-prune      # 只复制，不删目标端多余文件
    python -m review_tool mirror --force         # 覆盖目标端手工改过的同名文件

写作方向 ``local/ → MIRROR_DIR``（保持相对路径）；``ingest --mirror`` 是反向的
只读入口，从镜像读复盘 md。**local 始终是权威源**，本模块从不修改 local。

安全口径（v1.105.0）
--------------------
1. **只处理 git 未追踪文件**：``git ls-files --others`` + ``--others --ignored``，
   与 .gitignore 同一口径；git 不可用时回退为「排除 .gitkeep / README.md 全量」。
2. **`.env` 及其备份永不镜像**（凭据不外泄，.env / .env.bak-* / .env.* 全排除）。
3. **manifest + hash 守护**：目标目录的 ``.dailylumen-mirror.json`` 记录每个
   镜像文件的 sha256。同步删除只在三条件同时成立时发生：
   源已不存在 + 目标存在 + 目标当前 hash == manifest 记录（即用户没改过）。
   vault 原生笔记（不在 manifest）与用户手改过的文件一律保留。
4. **默认 dry-run**；`--apply` 才落盘。写 manifest 用临时文件 + os.replace。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections.abc import Iterable

from ..config import LOCAL_DIR, MIRROR_DIR

MANIFEST_NAME = ".dailylumen-mirror.json"
_TRACKED_FALLBACK = frozenset({".gitkeep", "README.md"})


def _is_env_file(name: str) -> bool:
    """.env 及其任何备份 / 变体（.env.bak-xxx / .env.local）都算凭据。"""
    return name == ".env" or name.startswith(".env.")


def _run_git(repo_root: str, *args: str) -> list[str] | None:
    """调 git 返回 NUL 分隔的文件路径；非 git 仓库 / 超时返回 None。"""
    try:
        proc = subprocess.run(
            ["git", "-C", repo_root, *args], capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return [p.decode("utf-8", "replace") for p in proc.stdout.split(b"\0") if p]


def untracked_files(local_dir: str = LOCAL_DIR) -> list[str]:
    """返回 local_dir 下所有 git 未追踪文件的绝对路径（含 ignored，排除 .env*）。

    与 .gitignore 同源：``--others --exclude-standard``（未追踪且非忽略）∪
    ``--others --ignored --exclude-standard``（未追踪且被忽略）。repo 根取
    local_dir 的父目录（即项目根）；git 不可用则回退为全量扫描减去两个占位。
    """
    repo_root = os.path.dirname(os.path.abspath(local_dir))
    rel_root = os.path.basename(os.path.abspath(local_dir))
    found: set[str] = set()
    out = _run_git(repo_root, "ls-files", "-z", "--others",
                   "--exclude-standard", "--", rel_root)
    if out is not None:
        found.update(out)
    out = _run_git(repo_root, "ls-files", "-z", "--others", "--ignored",
                   "--exclude-standard", "--", rel_root)
    if out is not None:
        found.update(out)
    if found:
        paths: list[str] = []
        for rel in found:
            if not rel or _is_env_file(os.path.basename(rel)):
                continue
            abs_p = os.path.normpath(os.path.join(repo_root, rel))
            if os.path.isfile(abs_p):
                paths.append(abs_p)
        return sorted(set(paths))

    # 回退：非 git 环境也要能跑（测试用临时目录 / 换机未 init 的场景）
    paths = []
    for root, _dirs, files in os.walk(local_dir):
        for name in files:
            if name in _TRACKED_FALLBACK or _is_env_file(name):
                continue
            p = os.path.join(root, name)
            if os.path.isfile(p) and not os.path.islink(p):
                paths.append(os.path.abspath(p))
    return sorted(paths)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _manifest_path(target_dir: str) -> str:
    return os.path.join(target_dir, MANIFEST_NAME)


def read_manifest(target_dir: str) -> dict[str, str]:
    """读 manifest（rel path → sha256）；不存在或损坏返回空 dict。"""
    p = _manifest_path(target_dir)
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, "rb") as f:
            data = json.loads(f.read().decode("utf-8"))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if isinstance(k, str)}
    except (OSError, ValueError, UnicodeDecodeError):
        pass
    return {}


def _write_manifest(target_dir: str, manifest: dict[str, str]) -> str:
    """原子写 manifest；返回写入路径（二进制 + LF + 回读校验）。"""
    os.makedirs(target_dir, exist_ok=True)
    path = _manifest_path(target_dir)
    tmp = path + ".tmp"
    payload = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True)
               + "\n").encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    with open(path, "rb") as f:
        if f.read() != payload:
            raise OSError(f"manifest 回读不一致: {path}")
    return path


def rel_of(path: str, local_dir: str = LOCAL_DIR) -> str:
    """绝对路径 → 相对 local_dir 的 POSIX 风格路径（跨盘符由调用方保证同根）。"""
    return os.path.relpath(path, local_dir).replace(os.sep, "/")


def plan_mirror(
    local_dir: str = LOCAL_DIR,
    target_dir: str = MIRROR_DIR,
    *,
    source_files: Iterable[str] | None = None,
    prune: bool = True,
    force: bool = False,
) -> dict:
    """计算镜像计划（纯计算，不写任何文件）。

    返回 ``{"copies": [(src, dst), ...], "deletes": [dst, ...],
    "unchanged": n, "conflicts": [(rel, reason), ...], "manifest": {...}}``。
    """
    local_dir = os.path.abspath(local_dir)
    target_dir = os.path.abspath(target_dir)
    # 目标不能是 local 自身或其祖先/子孙 —— 否则会自复制/自删
    try:
        common = os.path.commonpath([local_dir, target_dir])
    except ValueError:
        common = None  # 不同盘符：天然无包含关系
    if common in (local_dir, target_dir):
        raise ValueError(f"目标目录与 local 有包含关系，拒绝镜像: {target_dir}")

    srcs = list(source_files) if source_files is not None else untracked_files(local_dir)
    # 兜底：任何入口都不许把 .env* 写进镜像（凭据不外泄的红线）
    srcs = [p for p in srcs if not _is_env_file(os.path.basename(p))]
    src_rel = {rel_of(p, local_dir): p for p in srcs}
    old = read_manifest(target_dir)

    copies: list[tuple[str, str]] = []
    deletes: list[str] = []
    conflicts: list[tuple[str, str]] = []
    unchanged = 0
    new_manifest: dict[str, str] = {}

    for rel, src in src_rel.items():
        dst = os.path.join(target_dir, rel.replace("/", os.sep))
        digest = sha256_file(src)
        new_manifest[rel] = digest
        if not os.path.isfile(dst):
            copies.append((src, dst))
            continue
        dst_digest = sha256_file(dst)
        if dst_digest == digest:
            unchanged += 1
            continue
        # 目标有同名但内容不同：只在「我们放的且用户没改」时覆盖，或是 force
        if rel in old and old[rel] == dst_digest or force:
            copies.append((src, dst))
        else:
            reason = "目标端手工改过" if rel in old else "目标端已有非本系统文件"
            conflicts.append((rel, reason))

    if prune:
        for rel, digest in old.items():
            if rel in src_rel:
                continue
            dst = os.path.join(target_dir, rel.replace("/", os.sep))
            if not os.path.isfile(dst):
                continue
            if sha256_file(dst) == digest or force:
                deletes.append(dst)
            else:
                conflicts.append((rel, "目标端手工改过，跳过同步删除"))

    return {"copies": copies, "deletes": deletes, "unchanged": unchanged,
            "conflicts": conflicts, "manifest": new_manifest,
            "target_dir": target_dir, "local_dir": local_dir}


def apply_mirror(plan: dict) -> dict:
    """执行计划：复制 + 同步删除 + 刷新 manifest。返回结果统计。"""
    for src, dst in plan["copies"]:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    for dst in plan["deletes"]:
        os.remove(dst)
    _write_manifest(plan["target_dir"], plan["manifest"])
    return {"copied": len(plan["copies"]), "deleted": len(plan["deletes"]),
            "unchanged": plan["unchanged"], "conflicts": len(plan["conflicts"])}


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    apply = "--apply" in argv
    prune = "--no-prune" not in argv
    force = "--force" in argv
    target = MIRROR_DIR
    if "--target" in argv:
        i = argv.index("--target")
        if i + 1 >= len(argv):
            print("  [错误] --target 需要目录参数")
            return 2
        target = argv[i + 1]
    source = LOCAL_DIR
    if "--src" in argv:
        i = argv.index("--src")
        if i + 1 >= len(argv):
            print("  [错误] --src 需要目录参数")
            return 2
        source = argv[i + 1]

    try:
        p = plan_mirror(source, target, prune=prune, force=force)
    except ValueError as e:
        print(f"  [错误] {e}")
        return 2

    copies, deletes = p["copies"], p["deletes"]
    print(f"本地镜像: {p['local_dir']}  →  {p['target_dir']}")
    print(f"  [复制/更新] {len(copies)} 个   [同步删除] {len(deletes)} 个   "
          f"[未变] {p['unchanged']} 个   [冲突跳过] {len(p['conflicts'])} 个")
    for _src, dst in copies[:10]:
        print(f"    + {os.path.basename(dst)}")
    if len(copies) > 10:
        print(f"    … 另有 {len(copies) - 10} 个")
    for dst in deletes[:10]:
        print(f"    - {os.path.relpath(dst, p['target_dir'])}")
    for rel, reason in p["conflicts"][:5]:
        print(f"    ! {rel}（{reason}，--force 可覆盖）")

    if not apply:
        print("\nDRY-RUN：未写任何文件。加 --apply 执行。")
        return 0
    stats = apply_mirror(p)
    print(f"\n完成: 复制 {stats['copied']} / 删除 {stats['deleted']} / "
          f"未变 {stats['unchanged']} / 冲突跳过 {stats['conflicts']}")
    print(f"  manifest: {_manifest_path(p['target_dir'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

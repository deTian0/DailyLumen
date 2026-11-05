"""``python -m review_tool serve``：启动本机看板服务（默认 127.0.0.1:8765，只读，无鉴权）。"""
from __future__ import annotations

import argparse
import sys

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

_MISSING_HINT = (
    "serve 需要 Web 依赖（fastapi / uvicorn），当前环境未安装。\n"
    "  → uv sync --extra web   或   pip install -e .[web]"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m review_tool serve",
        description="启动 DailyLumen 本机看板（无鉴权；默认仅回环、只读）。",
    )
    p.add_argument("--host", default=DEFAULT_HOST, help=f"监听地址（默认 {DEFAULT_HOST}）")
    p.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"端口（默认 {DEFAULT_PORT}）")
    p.add_argument("--dist", default=None, help="前端构建目录（默认 web/dist）")
    p.add_argument("--enable-write", action="store_true", help="显式开启写接口（默认只读）")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        import uvicorn

        from .app import create_app
    except ImportError:
        print(_MISSING_HINT, file=sys.stderr)
        return 2

    allowed = set(_LOOPBACK)
    if args.host not in _LOOPBACK:
        allowed.add(args.host.lower())
        print(
            f"[!] 监听地址 {args.host} 不是回环地址：本服务【无鉴权】，"
            "同网段任何人都能读取你的复盘数据。除非明确知道后果，请改回 127.0.0.1。",
            file=sys.stderr,
        )
    if args.enable_write:
        print("[!] 已开启写接口：写操作仍需逐次确认（见 docs/Web看板PRD.md）。", file=sys.stderr)

    app = create_app(
        dist_dir=args.dist,
        write_enabled=args.enable_write,
        allowed_hosts=frozenset(allowed),
    )
    print(f"DailyLumen 看板：http://{args.host}:{args.port}/  （Ctrl+C 退出；无鉴权）")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0

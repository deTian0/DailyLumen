"""Web 看板：AI 评价预览 + mode 门禁（W8 / FR-H1 · FR-H2）。

约束：
- **只预览、不落盘**：调 ``reports.llm_review.run_llm_review(write=False, conn=只读连接)``，
  与 CLI ``llm-review DATE --dry-run`` 同源；``run_llm_review`` 在传入外部连接时拒绝 write。
- **mode 门禁**：``DAILYLUMEN_LLM_MODE != deepseek`` 时在调用前就拒绝（409 ``mode_gated``），
  不触网、不计费、不写 runlog。
- 错误文案只用固定中文，不回显上游异常原文（防止任何凭据片段被反射到响应）。
- 不依赖 fastapi / pydantic。
"""
from __future__ import annotations

from typing import Any

from .queries import QueryError, _check_date

_GATE_MSG = (
    "当前 mode=workbuddy：AI 评价由宿主按 skill daily-review-intake 撰写，"
    "看板不调 DeepSeek。如需在看板预览，请把 local/.env 设为 DAILYLUMEN_LLM_MODE=deepseek。"
)


def ai_status() -> dict[str, Any]:
    """门禁状态（不含任何凭据）：前端据此决定按钮可用与否。"""
    from ..config import get_llm_mode
    from ..integrations.flags import is_enabled

    mode = get_llm_mode()
    enabled = bool(is_enabled("deepseek"))
    allowed = mode == "deepseek" and enabled
    reason = None
    if mode != "deepseek":
        reason = _GATE_MSG
    elif not enabled:
        reason = "DeepSeek 集成未开启（local/.env 的集成开关）"
    return {"mode": mode, "allowed": allowed, "reason": reason}


def review_preview(conn, day: str | None = None, *, client=None, mode: str | None = None
                   ) -> dict[str, Any]:
    """= ``llm-review DAY --dry-run``：返回将写入「七、AI」的草稿与新旧差异，不写 md / 库。"""
    from ..pipeline.deepseek import DeepSeekCredError, DeepSeekError, DeepSeekModeError
    from ..reports.ai_review import build_context
    from ..reports.llm_review import run_llm_review

    st = ai_status()
    eff_mode = mode or st["mode"]
    if eff_mode != "deepseek":
        raise QueryError(409, "mode_gated", _GATE_MSG)
    if mode is None and not st["allowed"]:
        raise QueryError(409, "ai_disabled", st["reason"] or "AI 未开启")

    if day is None:
        day = build_context(None, conn=conn)["date"]
    _check_date(day)
    try:
        res = run_llm_review(day, write=False, conn=conn, client=client, mode=eff_mode)
    except DeepSeekModeError as e:
        raise QueryError(409, "mode_gated", _GATE_MSG) from e
    except DeepSeekCredError as e:
        raise QueryError(503, "ai_cred", "DeepSeek 凭据缺失或失效，请检查 local/.env") from e
    except (DeepSeekError, OSError) as e:
        # OSError：裸 socket 超时等未被 client 包装的网络错误；同样只回固定文案
        raise QueryError(502, "ai_upstream", "DeepSeek 调用失败（限流 / 网络 / 上游错误），请稍后重试") from e
    return {
        "date": res["day"],
        "section": res["section"],
        "old_section": res["old_section"],
        "diff_text": res["diff_text"],
        "context_empty": res["context_empty"],
        "flags": res["flags"],
        "written": False,
        "cli": f"python -m review_tool llm-review {res['day']} --write",
    }

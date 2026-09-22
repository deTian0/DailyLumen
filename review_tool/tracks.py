"""个人打卡项归一化。

背景（为什么需要它）
------------------
打卡项的原始写法是自由文本（「晨间-CoQ10 ×1 ＋ Exia 早3」这种），
直接当主键会让同一个规范项裂成好几种形态，依从率无法聚合。
本模块把任意写法映射到 ``config.PERSONAL_ITEMS`` 里的规范 ID：

    输入文本                              归一化结果
    ------------------------------------  -----------------------------
    「晨间」小节 + 『CoQ10 ×1 ＋ Exia 早3』   coq10@morning, exia_am@morning
    「晚间」小节 + 『Exia 晚3 ＋ Move Free』   exia_pm@evening, movefree@evening
    无小节      + 『Move Free 红色 ×1』       movefree            （时段未知）
    任意        + 『护肤』                    skincare

key 规则
--------
- ``item_key``  规范项 ID（coq10 / exia_am / vitb / exia_pm / movefree / skincare）
- ``track_key`` ``item_key``，若时段明确则追加 ``@<slot>``

未知写法不会被丢弃：用 slug 生成稳定的 ``other:<slug>``，同样可以聚合。
"""
from __future__ import annotations

import re

from .config import PERSONAL_ITEMS, SLOT_BY_CN, SUPPLEMENT_MARKER
from .util import slugify, split_items

# alias -> 规范项，按 alias 长度降序（长 alias 优先，避免「Exia 早」抢走「Exia 早3」）
_ALIAS_INDEX: list[tuple[str, dict]] = sorted(
    ((alias, item) for item in PERSONAL_ITEMS for alias in item["aliases"]),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

# 旧数据的时段前缀：「晨间-」「午间-」「晚间-」
_LEGACY_SLOT_RE = re.compile(r"^\s*(晨间|午间|晚间)\s*[-－—]\s*")


def resolve_item(fragment: str) -> dict | None:
    """在 PERSONAL_ITEMS 中匹配文本片段；未命中返回 None。"""
    text = str(fragment or "")
    for alias, item in _ALIAS_INDEX:
        if alias in text:
            return item
    return None


def make_track_key(item_key: str, slot: str | None) -> str:
    """规范项 ID + 时段 -> track_key（时段未知时不加后缀）。"""
    return f"{item_key}@{slot}" if slot else item_key


def resolve_track(fragment: str, slot: str | None = None,
                  category: str = "服药") -> tuple[str, str, str, str]:
    """单个打卡片段 -> ``(category, track_key, item_key, item_label)``。

    :param fragment: 片段文本，如 ``CoQ10 ×1``
    :param slot: 当前小节的时段 key（morning/noon/evening），没有则 None
    :param category: 未命中已知项时使用的兜底类别

    时段归属规则（见 config.PERSONAL_ITEMS 的 per_slot 说明）：
    - ``per_slot=True`` 的项跟随小节标题；标题缺失 => 时段未知（裸 key）
    - ``per_slot=False`` 的项固定用自己定义的时段（可为 None = 不分时段）
    - 未命中的未知项，跟随小节标题
    """
    item = resolve_item(fragment)
    if item is not None:
        item_key = item["key"]
        if item.get("per_slot"):
            effective_slot = slot
        else:
            effective_slot = item.get("slot")
        return (
            item["category"],
            make_track_key(item_key, effective_slot),
            item_key,
            item["label"],
        )

    # 未知项：用 slug 生成稳定 ID，保证仍可聚合
    slug = slugify(fragment)
    item_key = f"other:{slug}"
    return (category, make_track_key(item_key, slot), item_key, str(fragment).strip())


def normalize_supplement_line(text: str, slot: str | None = None
                              ) -> list[tuple[str, str, str, str]]:
    """拆解一行「补剂」打卡 -> 若干规范项。

    文本形如 ``补剂：CoQ10 ×1 ＋ Exia 早3``，先去掉「补剂」前缀，
    再按 ＋ / + / 、 / / 拆分，逐段归一化。
    """
    if SUPPLEMENT_MARKER not in text:
        return []
    spec = re.split(r"[：:]", text, maxsplit=1)[-1].strip()
    return [
        resolve_track(frag, slot=slot, category="服药")
        for frag in split_items(spec)
    ]


def normalize_legacy_item(item: str, category: str
                          ) -> list[tuple[str, str, str, str]]:
    """把历史 ``personal_tracks.item`` 文本归一化（供数据迁移使用）。

    旧记录的 item 可能是「晨间-CoQ10 ×1 ＋ Exia 早3」这种带时段前缀的
    多合一条目，因此**一条旧记录可能裂成多条规范记录**——这正是归一化的目的。
    """
    text = str(item or "").strip()
    slot = None
    m = _LEGACY_SLOT_RE.match(text)
    if m:
        slot = SLOT_BY_CN.get(m.group(1))
        text = _LEGACY_SLOT_RE.sub("", text, count=1).strip()

    if not text:
        return [resolve_track(item, slot=slot, category=category)]

    if category == "服药" or SUPPLEMENT_MARKER in text:
        # 裸「补剂」这种无具体项的旧记录：保留为未知项而非丢弃
        parts = split_items(text)
        if not parts:
            parts = [text]
        return [resolve_track(p, slot=slot, category="服药") for p in parts]

    return [resolve_track(text, slot=slot, category=category)]

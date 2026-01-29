"""Pure model helpers for the Find Everything launcher."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class FindItem:
    kind: str
    item_id: str
    title: str
    subtitle: str
    keywords: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FindResult:
    kind: str
    item_id: str
    title: str
    subtitle: str


@dataclass(frozen=True, slots=True)
class FindGroup:
    name: str
    rows: tuple[FindResult, ...]


@dataclass(frozen=True, slots=True)
class FindDisplayRow:
    kind: str  # "header" | "row" | "footer"
    text: str
    row_index: int | None = None


@dataclass(frozen=True, slots=True)
class FindView:
    query: str
    results: tuple[FindResult, ...]
    selection_index: int


GROUP_ORDER: tuple[tuple[str, str], ...] = (
    ("command", "Commands"),
    ("scene", "Scenes"),
    ("entity", "Entities"),
    ("asset", "Assets"),
    ("problem", "Problems"),
)


def build_find_items(
    *,
    commands: Iterable[Any],
    scenes: Iterable[Any],
    entities: Iterable[Any],
    assets: Iterable[Any],
    problems: Iterable[Any],
) -> list[FindItem]:
    items: list[FindItem] = []

    for cmd in commands:
        cmd_id = str(getattr(cmd, "id", "") or "").strip()
        title = str(getattr(cmd, "title", "") or "").strip()
        keywords = getattr(cmd, "keywords", ()) or ()
        if not cmd_id or not title:
            continue
        kw_list = [str(k).strip() for k in keywords if str(k).strip()]
        items.append(
            FindItem(
                kind="command",
                item_id=cmd_id,
                title=title,
                subtitle="",
                keywords=tuple(kw_list),
            )
        )

    for row in scenes:
        scene_id = str(getattr(row, "scene_id", "") or "").strip()
        display = str(getattr(row, "display_name", "") or "").strip() or scene_id
        pack_name = str(getattr(row, "pack_name", "") or "").strip()
        subtitle = scene_id
        keywords = [scene_id, display, pack_name]
        if not scene_id:
            continue
        items.append(
            FindItem(
                kind="scene",
                item_id=scene_id,
                title=display,
                subtitle=subtitle,
                keywords=tuple(k for k in keywords if k),
            )
        )

    for entity in entities:
        entity_id = str(getattr(entity, "id", "") or "").strip()
        name = str(getattr(entity, "name", "") or "").strip()
        etype = str(getattr(entity, "type", "") or "").strip()
        if not entity_id:
            continue
        subtitle = name or etype
        keywords = [entity_id, name, etype]
        items.append(
            FindItem(
                kind="entity",
                item_id=entity_id,
                title=entity_id,
                subtitle=subtitle,
                keywords=tuple(k for k in keywords if k),
            )
        )

    for row in assets:
        rel_path = str(getattr(row, "rel_path", "") or "").strip()
        display = str(getattr(row, "display_name", "") or "").strip()
        kind = str(getattr(row, "kind", "") or "").strip()
        if not rel_path:
            continue
        keywords = [rel_path, display, kind]
        items.append(
            FindItem(
                kind="asset",
                item_id=rel_path,
                title=rel_path,
                subtitle=kind,
                keywords=tuple(k for k in keywords if k),
            )
        )

    for issue in problems:
        issue_id = str(getattr(issue, "issue_id", "") or "").strip()
        message = str(getattr(issue, "message", "") or "").strip()
        kind = str(getattr(issue, "kind", "") or "").strip()
        entity_id = str(getattr(issue, "entity_id", "") or "").strip()
        if not issue_id or not message:
            continue
        keywords = [issue_id, message, kind, entity_id]
        items.append(
            FindItem(
                kind="problem",
                item_id=issue_id,
                title=message,
                subtitle=kind,
                keywords=tuple(k for k in keywords if k),
            )
        )

    return items


def fuzzy_score(query: str, item: FindItem) -> tuple[int, int, int, str] | None:
    q = _normalize_query(query)
    if not q:
        return (0, 0, len(item.title), item.title.lower())

    title = item.title.lower()
    subtitle = item.subtitle.lower()

    score = _score_field(title, q, base_rank=0)
    if score is not None:
        return (*score, len(title), title)

    score = _score_field(subtitle, q, base_rank=2)
    if score is not None:
        return (*score, len(title), title)

    best_kw: tuple[int, int] | None = None
    for kw in item.keywords:
        kw_l = str(kw).strip().lower()
        score = _score_field(kw_l, q, base_rank=4)
        if score is None:
            continue
        if best_kw is None or score < best_kw:
            best_kw = score
    if best_kw is not None:
        return (*best_kw, len(title), title)

    return None


def filter_find_items(items: Iterable[FindItem], query: str, *, limit: int | None = 10) -> list[FindResult]:
    results: list[FindResult] = []
    q = _normalize_query(query)
    indexed = list(items)

    if not q:
        limited_items = indexed if limit is None else indexed[:limit]
        for item in limited_items:
            results.append(_to_result(item))
        return results

    scored: list[tuple[tuple[int, int, int, str, int], FindItem]] = []
    for idx, item in enumerate(indexed):
        score = fuzzy_score(q, item)
        if score is None:
            continue
        scored.append(((*score, idx), item))

    scored.sort(key=lambda pair: pair[0])
    limited_scored = scored if limit is None else scored[:limit]
    for _score, item in limited_scored:
        results.append(_to_result(item))
    return results


def build_find_groups(
    rows: Iterable[FindResult],
    *,
    group_order: tuple[tuple[str, str], ...] = GROUP_ORDER,
) -> list[FindGroup]:
    buckets: dict[str, list[FindResult]] = {key: [] for key, _label in group_order}
    for row in rows:
        if row.kind in buckets:
            buckets[row.kind].append(row)

    groups: list[FindGroup] = []
    for key, label in group_order:
        items = buckets.get(key, [])
        if not items:
            continue
        groups.append(FindGroup(name=label, rows=tuple(items)))
    return groups


def flatten_find_groups(groups: Iterable[FindGroup]) -> list[FindResult]:
    rows: list[FindResult] = []
    for group in groups:
        rows.extend(group.rows)
    return rows


def compute_find_counts(
    rows: Iterable[FindResult],
    *,
    group_order: tuple[tuple[str, str], ...] = GROUP_ORDER,
    include_zero: bool = True,
) -> dict[str, object]:
    counts: dict[str, int] = {label: 0 for _key, label in group_order}
    total = 0
    for row in rows:
        total += 1
        for key, label in group_order:
            if row.kind == key:
                counts[label] += 1
                break
    if not include_zero:
        counts = {label: count for label, count in counts.items() if count > 0}
    return {"total": total, "by_group": counts}


def build_find_display_rows(
    rows: Iterable[FindResult],
    counts: dict[str, object],
    *,
    group_order: tuple[tuple[str, str], ...] = GROUP_ORDER,
) -> list[FindDisplayRow]:
    display: list[FindDisplayRow] = []
    by_group = counts.get("by_group")
    if not isinstance(by_group, dict):
        by_group = {}

    groups = build_find_groups(rows, group_order=group_order)
    row_index = 0
    for group in groups:
        count = int(by_group.get(group.name, len(group.rows)))
        display.append(FindDisplayRow(kind="header", text=f"{group.name.upper()} ({count})"))
        for row in group.rows:
            subtitle = str(row.subtitle or "")
            if subtitle:
                text = f"{row.title} - {subtitle}"
            else:
                text = row.title
            display.append(FindDisplayRow(kind="row", text=text, row_index=row_index))
            row_index += 1

    total_count = _coerce_int(counts.get("total", 0))
    parts = [f"{total_count} results"]
    for _key, label in group_order:
        group_value = _coerce_int(by_group.get(label, 0))
        parts.append(f"{label} {group_value}")
    footer = " | ".join(parts)
    display.append(FindDisplayRow(kind="footer", text=footer))
    return display


def _coerce_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def build_find_everything_hint_line(input_source: str) -> str:
    source = str(input_source or "").strip().lower()
    if source == "gamepad":
        return "A: Open   B: Close   D-pad: Navigate"
    return "Enter: Open   Esc: Close   Up/Down: Navigate"


def clamp_selection(index: int, count: int) -> int:
    if count <= 0:
        return -1
    return max(0, min(index, count - 1))


def move_selection(index: int, delta: int, count: int) -> int:
    if count <= 0:
        return -1
    if index < 0:
        index = 0
    return (index + delta) % count


def _normalize_query(query: str) -> str:
    return " ".join(str(query or "").strip().lower().split())


def _score_field(text: str, query: str, *, base_rank: int) -> tuple[int, int] | None:
    if not text:
        return None
    if text.startswith(query):
        return (base_rank, 0)
    pos = text.find(query)
    if pos >= 0:
        return (base_rank + 1, pos)
    return None


def _to_result(item: FindItem) -> FindResult:
    prefix = {
        "command": "Command",
        "scene": "Scene",
        "entity": "Entity",
        "asset": "Asset",
        "problem": "Problem",
    }.get(item.kind, item.kind.title())
    title = f"{prefix}: {item.title}"
    return FindResult(
        kind=item.kind,
        item_id=item.item_id,
        title=title,
        subtitle=item.subtitle,
    )

"""Prefab palette helpers for filtering and tag handling."""

from __future__ import annotations

from typing import Any, Iterable


def parse_palette_filter(raw: str) -> tuple[list[str], list[str]]:
    """Parse palette filter string into (free_text_terms, tag_terms).

    Supported tag tokens:
    - #tag
    - t:tag

    Whitespace separates tokens. Tokens are case-insensitive.
    """
    text = str(raw or "").strip()
    if not text:
        return ([], [])
    terms: list[str] = []
    tags: list[str] = []
    for tok in text.split():
        t = str(tok or "").strip()
        if not t:
            continue
        lower = t.lower()
        tag: str | None = None
        if lower.startswith("#") and len(lower) > 1:
            tag = lower[1:]
        elif lower.startswith("t:") and len(lower) > 2:
            tag = lower[2:]
        if tag:
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
        else:
            terms.append(lower)
    return (terms, tags)


def filter_prefab_palette_items(items: list[dict[str, Any]], raw_filter: str) -> list[dict[str, Any]]:
    """Filter prefabs by free-text and/or tags.

    - Tags: all specified tags must be present (case-insensitive)
    - Free-text: each term must match (contains) at least one of the existing fields
      (id/display_name). Empty filter returns items unchanged.
    """
    raw = str(raw_filter or "").strip()
    if not raw:
        return list(items)
    terms, required_tags = parse_palette_filter(raw)
    if not terms and not required_tags:
        return list(items)

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        # Tag match
        if required_tags:
            tags_val = item.get("tags")
            if not isinstance(tags_val, list):
                tags_val = []
            tag_list = [str(t or "").strip().lower() for t in tags_val if str(t or "").strip()]
            # ANDed prefix match: each requested token must match at least one prefab tag.
            if not all(any(t.startswith(req) for t in tag_list) for req in required_tags):
                continue

        # Free-text match
        if terms:
            display_name = str(item.get("display_name") or "").lower()
            prefab_id = str(item.get("id") or "").lower()
            hay = f"{display_name} {prefab_id}"
            if not all(term in hay for term in terms):
                continue

        out.append(item)
    return out


def palette_tag_frequencies(prefabs: list[dict[str, Any]]) -> list[str]:
    """Return tags sorted by descending count, then alphabetical (stable)."""
    counts: dict[str, int] = {}
    for p in prefabs:
        if not isinstance(p, dict):
            continue
        tags_val = p.get("tags")
        if not isinstance(tags_val, list):
            continue
        unique = {
            str(t or "").strip().lower()
            for t in tags_val
            if isinstance(t, str) and str(t).strip()
        }
        for t in unique:
            counts[t] = counts.get(t, 0) + 1

    return sorted(counts.keys(), key=lambda t: (-counts.get(t, 0), t))


def normalize_entity_panel_tags(value: Any) -> list[str]:
    """Normalize tags value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.replace(";", ",").split(",")]
        return [part for part in parts if part]
    if isinstance(value, Iterable):
        tags: list[str] = []
        for entry in value:
            if not isinstance(entry, str):
                continue
            cleaned = entry.strip()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)
        return tags
    return []


def apply_entity_panel_tag_delta(
    tags: list[str],
    *,
    add: list[str] | None = None,
    remove: list[str] | None = None,
) -> list[str]:
    """Apply add/remove delta to tag list."""
    updated = list(tags)
    if add:
        for tag in add:
            if tag not in updated:
                updated.append(tag)
    if remove:
        remove_set = set(remove)
        updated = [tag for tag in updated if tag not in remove_set]
    return updated

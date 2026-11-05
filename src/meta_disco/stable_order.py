"""Orders taken from what a list holds rather than from the order it arrived in (#732, #750, #767)."""

from __future__ import annotations

import bisect
import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any


def most_frequent(
    counts: Mapping[Any, int], limit: int | None = None, key: Callable[[Any], Any] = lambda k: k
) -> dict[Any, int]:
    """``counts`` most frequent first, ties by ``key`` of the key."""
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], key(kv[0])))
    return dict(ranked if limit is None else ranked[:limit])


def example_order(example: Any) -> str:
    """A string itself, anything else its JSON with sorted keys."""
    return example if isinstance(example, str) else json.dumps(example, sort_keys=True)


def by_file_name(example: Mapping[str, Any]) -> tuple[str, str]:
    """An example naming a file: by its ``file_name``, then by content."""
    return str(example["file_name"]), example_order(example)


def keep_smallest(examples: list, example: Any, limit: int, key: Callable[[Any], Any] = example_order) -> None:
    """Add ``example`` to ``examples`` unless it is there, kept in ``key`` order and cut to the ``limit`` smallest."""
    if example not in examples:
        bisect.insort(examples, example, key=key)
        del examples[limit:]


def past_smallest(examples: Sequence[Mapping[str, Any]], file_name: str, limit: int) -> bool:
    """Whether an example naming ``file_name`` would be cut from ``examples`` (kept :func:`by_file_name`), so it need
    not be built."""
    return len(examples) >= limit and str(examples[-1]["file_name"]) < file_name

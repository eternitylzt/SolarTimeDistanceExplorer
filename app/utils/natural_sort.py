"""Natural filename ordering used only when observational times are absent."""

from __future__ import annotations

import re
from pathlib import Path

_SPLIT_NUMBERS = re.compile(r"(\d+)")


def natural_key(path: str | Path) -> list[object]:
    """Return a case-insensitive natural-sort key for a filename."""
    name = Path(path).name.casefold()
    return [int(part) if part.isdigit() else part for part in _SPLIT_NUMBERS.split(name)]

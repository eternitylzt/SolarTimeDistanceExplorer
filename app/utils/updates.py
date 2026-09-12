"""Validation for the public, manually requested GitHub release response."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

RELEASES_URL = "https://github.com/eternitylzt/SolarTimeDistanceExplorer/releases"
LATEST_RELEASE_API = "https://api.github.com/repos/eternitylzt/SolarTimeDistanceExplorer/releases/latest"


def version_tuple(value: str) -> tuple[int, int, int]:
    """Compare stable numeric release tags, so 1.10.0 sorts after 1.9.0."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)(?:\.(\d+))?", value.strip())
    if match is None:
        raise ValueError("Invalid stable release version.")
    return (int(match[1]), int(match[2]), int(match[3] or 0))


@dataclass(frozen=True)
class ReleaseInfo:
    tag: str
    url: str

    def is_newer_than(self, current: str) -> bool:
        return version_tuple(self.tag) > version_tuple(current)


def parse_release(payload: bytes) -> ReleaseInfo:
    """Accept a stable published release and its exact repository download page."""
    try:
        data = json.loads(payload)
        tag = data["tag_name"]
        url = data["html_url"]
        version_tuple(tag)
        if data.get("draft") or data.get("prerelease") or url != f"{RELEASES_URL}/tag/{tag}":
            raise ValueError("Unexpected release information.")
        return ReleaseInfo(tag, url)
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("GitHub returned invalid release information.") from exc

"""Save and restore reproducible application state in .stdproj JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from astropy.time import Time

from app.data.base import TimeSeriesDataset
from app.paths.base import PathGeometry
from app.regions.base import RegionGeometry


def save_project(
    path: str | Path,
    dataset: TimeSeriesDataset,
    paths: list[PathGeometry],
    active_path_id: str | None,
    reference_frame: int,
    display_settings: dict[str, Any],
    td_display_settings: dict[str, Any],
    regions: list[RegionGeometry] | None = None,
) -> None:
    """Persist UI/scientific settings but never duplicate large source arrays."""
    payload = {
        "format": "SolarTimeDistanceExplorerProject",
        "version": 2,
        "dataset": dataset.project_descriptor(),
        "time": {
            "unix": dataset.times.unix.tolist() if dataset.times is not None else None,
            "scale": dataset.times.scale if dataset.times is not None else None,
        },
        "paths": [item.to_dict() for item in paths],
        "active_path_id": active_path_id,
        "reference_frame": int(reference_frame),
        "display_settings": display_settings,
        "td_display_settings": td_display_settings,
        "regions": [item.to_dict() for item in (regions or [])],
    }
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_project(path: str | Path) -> dict[str, Any]:
    """Read basic validated project JSON; source reopening is handled by factory."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("format") != "SolarTimeDistanceExplorerProject":
        raise ValueError("This is not a Solar Time–Distance Explorer project.")
    return payload


def restore_times(dataset: TimeSeriesDataset, payload: dict[str, Any]) -> None:
    """Restore project time values exactly when the source length still agrees."""
    source = payload.get("time", {})
    values = source.get("unix")
    if values is None or len(values) != dataset.n_frames:
        return
    dataset.set_times(Time(values, format="unix", scale=source.get("scale") or "utc"))

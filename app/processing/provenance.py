"""One provenance schema shared by numerical results and figure sidecars."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
from app.data.base import TimeSeriesDataset
from app.version import __version__


def result_provenance(dataset: TimeSeriesDataset, parameters: dict[str, Any]) -> dict[str, Any]:
    """Identify ordered input files with size/mtime, without hashing large cubes."""
    files = list(dict.fromkeys(dataset.get_frame_metadata(i).source for i in range(dataset.n_frames)))
    records = []
    for name in files:
        path = Path(name)
        record: dict[str, Any] = {"path": str(path)}
        if path.is_file():
            stat = path.stat()
            record.update(size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)
        records.append(record)
    times = dataset.times
    return {
        "schema": "STDE-provenance-1", "software_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "dataset": dataset.project_descriptor(), "source_files": records,
        "time_scale": times.scale if times is not None else "frame",
        "time_origin": getattr(dataset, "time_origin", "source"),
        "time_jd1": times.jd1.tolist() if times is not None else None,
        "time_jd2": times.jd2.tolist() if times is not None else None,
        "parameters": parameters,
        "distance_conversion": {"solar_radius_km": 695700.0, "angular_radius_arcsec": 959.63,
                                "basis": "nominal projected solar scale; not deprojected"},
        "source_identity": "size/mtime, not cryptographic content verification",
    }


def write_sidecar(target: str | Path, metadata: dict[str, Any]) -> Path:
    """Use the same sidecar naming for figures and numerical products."""
    destination = Path(str(target) + ".json")
    destination.write_text(json.dumps(metadata, indent=2, ensure_ascii=True,
        default=lambda v: v.tolist() if isinstance(v, np.ndarray) else v.item() if isinstance(v, np.generic) else str(v)), encoding="utf-8")
    return destination

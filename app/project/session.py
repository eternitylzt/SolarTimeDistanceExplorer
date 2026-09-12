"""Portable analysis sessions: JSON plus compressed NPY, never pickle or FITS cubes."""
from __future__ import annotations

import base64
from dataclasses import fields, is_dataclass
from io import BytesIO
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any
from zipfile import ZipFile, ZIP_DEFLATED
import numpy as np
from astropy.time import Time
from app.processing.td_generator import TDResult
from app.processing.region_analysis import RegionTrendResult, RegionHistogramResult, RegionHistogramSequence

RESULT_TYPES = {c.__name__: c for c in (TDResult, RegionTrendResult, RegionHistogramResult, RegionHistogramSequence)}


def save_session(path: str | Path, state: dict[str, Any]) -> None:
    """Atomically store a session. Repeated arrays are written once by identity."""
    target = Path(path)
    with NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as temp:
        temporary = Path(temp.name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=3) as archive:
            arrays: dict[int, str] = {}
            array_references: list[np.ndarray] = []
            def encode(value: Any) -> Any:
                if isinstance(value, Time):
                    return {"_time": True, "jd1": encode(np.asarray(value.jd1)),
                            "jd2": encode(np.asarray(value.jd2)), "scale": value.scale}
                if isinstance(value, np.ndarray):
                    if value.dtype.hasobject:
                        raise ValueError("Object arrays are not supported in analysis sessions.")
                    key = id(value)
                    if key not in arrays:
                        name = f"arrays/{len(arrays)}.npy"; arrays[key] = name
                        # Keep temporary Time.jd arrays alive: otherwise Python
                        # can recycle an id and falsely deduplicate jd1 and jd2.
                        array_references.append(value)
                        buffer = BytesIO(); np.save(buffer, value, allow_pickle=False)
                        archive.writestr(name, buffer.getvalue())
                    return {"_array": arrays[key]}
                if is_dataclass(value) and type(value).__name__ in RESULT_TYPES:
                    return {"_result": type(value).__name__, "fields": {f.name: encode(getattr(value, f.name)) for f in fields(value)}}
                if isinstance(value, bytes):
                    return {"_bytes": base64.b64encode(value).decode("ascii")}
                if isinstance(value, np.generic):
                    return value.item()
                if isinstance(value, (tuple, list)):
                    return [encode(v) for v in value]
                if isinstance(value, dict):
                    return {str(k): encode(v) for k, v in value.items()}
                if value is None or isinstance(value, (str, bool, float, int)):
                    return value
                raise TypeError(f"Unsupported session value: {type(value).__name__}")
            manifest = {"format": "STDE-analysis-session", "version": 1, "state": encode(state)}
            archive.writestr("session.json", json.dumps(manifest))
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def load_session(path: str | Path) -> dict[str, Any]:
    """Read an explicit allowlist of products without extracting archive paths."""
    with ZipFile(path) as archive:
        if sum(i.file_size for i in archive.infolist()) > 2 * 1024**3:
            raise ValueError("Session exceeds the 2 GiB uncompressed safety limit.")
        payload = json.loads(archive.read("session.json"))
        if payload.get("format") != "STDE-analysis-session" or payload.get("version") != 1:
            raise ValueError("Unsupported analysis session format.")
        arrays: dict[str, np.ndarray] = {}
        def decode(value: Any) -> Any:
            if isinstance(value, list):
                return [decode(v) for v in value]
            if not isinstance(value, dict):
                return value
            if "_array" in value:
                name = value["_array"]
                if name not in arrays:
                    arrays[name] = np.load(BytesIO(archive.read(name)), allow_pickle=False)
                return arrays[name]
            if "_time" in value:
                return Time(decode(value["jd1"]), decode(value["jd2"]), format="jd", scale=value["scale"])
            if "_bytes" in value:
                return base64.b64decode(value["_bytes"], validate=True)
            if "_result" in value:
                cls = RESULT_TYPES.get(value["_result"])
                if cls is None:
                    raise ValueError("Unsupported result type.")
                return cls(**decode(value["fields"]))
            return {k: decode(v) for k, v in value.items()}
        return decode(payload["state"])

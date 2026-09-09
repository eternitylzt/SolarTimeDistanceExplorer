"""IDL SAV sources, including standard SolarSoft map structures."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS
from scipy.io import readsav

from app.data.base import TimeSeriesDataset
from app.data.metadata import FrameMetadata, TimeAxisDetection
from app.data.solar_map import make_solar_map
from app.data.time_parser import times_from_array

SSW_REQUIRED_TAGS = {"data", "xc", "yc", "dx", "dy"}


def inspect_sav(path: str | Path) -> dict[str, tuple[str, tuple[int, ...], str]]:
    """List SAV variables and identify numeric arrays or SSW map structures."""
    values = readsav(str(path), python_dict=True)
    output: dict[str, tuple[str, tuple[int, ...], str]] = {}
    for name, value in values.items():
        array = np.asarray(value)
        if is_ssw_map_structure(value):
            category = "SSW map structure"
        elif array.ndim == 3 and np.issubdtype(array.dtype, np.number):
            category = "candidate cube"
        elif array.ndim == 2 and np.issubdtype(array.dtype, np.number):
            category = "candidate image (pixel axes)"
        else:
            category = "other"
        output[name] = (str(array.dtype), tuple(array.shape), category)
    return output


def is_ssw_map_structure(value: Any) -> bool:
    """Recognize the documented SSW map core tags DATA/XC/YC/DX/DY."""
    return SSW_REQUIRED_TAGS.issubset(_field_names(value))


def detect_sav_time_axis(array: np.ndarray) -> TimeAxisDetection:
    """Use the same deliberately low-confidence shape heuristic for SAV cubes."""
    sizes = list(array.shape)
    minimum = min(sizes)
    if sizes.count(minimum) == 1:
        return TimeAxisDetection(sizes.index(minimum), "Low", "Unique smallest dimension heuristic.")
    return TimeAxisDetection(None, "Uncertain", "SAV has no FITS CTYPE; select an axis.")


class SavCubeDataset(TimeSeriesDataset):
    """Selected three-dimensional numeric SAV variable exposed as 2-D frames."""

    source_type = "sav_cube"

    def __init__(self, path: str | Path, variable: str, time_axis: int, time_variable: str | None = None) -> None:
        path = Path(path)
        values = readsav(str(path), python_dict=True)
        if variable not in values:
            raise ValueError(f"SAV variable {variable!r} is not present.")
        self.variable = variable
        self.time_variable = time_variable
        self._cube = np.asarray(values[variable], dtype=float)
        if self._cube.ndim != 3:
            raise ValueError(f"Selected SAV variable has shape {self._cube.shape}; it is not 3-D.")
        if time_axis not in (0, 1, 2):
            raise ValueError("Time axis must be 0, 1, or 2.")
        self.time_axis = time_axis
        self.detection = detect_sav_time_axis(self._cube)
        times = times_from_array(values[time_variable]) if time_variable and time_variable in values else None
        if times is not None and len(times) != self._cube.shape[time_axis]:
            times = None
        shape = tuple(self._cube.shape[axis] for axis in range(3) if axis != time_axis)
        metadata = [
            FrameMetadata(source=str(path), time=times[i] if times is not None else None, shape=shape)
            for i in range(self._cube.shape[time_axis])
        ]
        self.map_notice = (
            "所选 SAV 变量不是标准 SSW Map 结构体（DATA/XC/YC/DX/DY）；"
            "图像数据仍可使用，但坐标轴为像素。"
        )
        super().__init__(path, times, metadata, shape)

    def get_frame(self, index: int) -> np.ndarray:
        if not 0 <= index < self.n_frames:
            raise IndexError(index)
        return np.asarray(np.take(self._cube, index, axis=self.time_axis), dtype=float)

    def get_wcs(self, index: int) -> WCS | None:
        return None

    def project_descriptor(self) -> dict[str, Any]:
        output = super().project_descriptor()
        output.update({"variable": self.variable, "time_axis": self.time_axis, "time_variable": self.time_variable})
        return output


class SavImageDataset(TimeSeriesDataset):
    """Fallback preview for a non-SSW numeric 2-D SAV variable."""

    source_type = "sav_image"

    def __init__(self, path: str | Path, variable: str) -> None:
        path = Path(path)
        values = readsav(str(path), python_dict=True)
        self.variable = variable
        self._frame = np.asarray(values[variable], dtype=float)
        if self._frame.ndim != 2:
            raise ValueError(f"Selected SAV variable has shape {self._frame.shape}; it is not a 2-D image.")
        self.map_notice = (
            "该变量是数值图像，但不是标准 SSW Map 结构体（DATA/XC/YC/DX/DY）。"
            "当前使用像素坐标显示。"
        )
        metadata = [FrameMetadata(source=str(path), time=None, shape=self._frame.shape)]
        super().__init__(path, None, metadata, self._frame.shape)

    def get_frame(self, index: int) -> np.ndarray:
        if index != 0:
            raise IndexError(index)
        return self._frame

    def get_wcs(self, index: int) -> WCS | None:
        return None

    def project_descriptor(self) -> dict[str, Any]:
        output = super().project_descriptor()
        output["variable"] = self.variable
        return output


class SavMapDataset(TimeSeriesDataset):
    """One or more documented SSW map structures converted to SunPy maps."""

    source_type = "sav_ssw_map"

    def __init__(self, path: str | Path, variable: str) -> None:
        path = Path(path)
        values = readsav(str(path), python_dict=True)
        if variable not in values or not is_ssw_map_structure(values[variable]):
            raise ValueError("The selected variable is not a standard SSW map structure.")
        self.variable = variable
        records = _records(values[variable])
        self._frames: list[np.ndarray] = []
        self._headers: list[dict[str, Any]] = []
        parsed_times: list[Time | None] = []
        for record in records:
            data = _numeric_2d(_field(record, "data"))
            header, obstime = _ssw_header(record, data.shape)
            self._frames.append(data)
            self._headers.append(header)
            parsed_times.append(obstime)
        if not self._frames:
            raise ValueError("The SSW map structure contains no two-dimensional DATA image.")
        shape = self._frames[0].shape
        if any(frame.shape != shape for frame in self._frames):
            raise ValueError("SSW map records have inconsistent DATA shapes.")
        times = Time(parsed_times) if all(item is not None for item in parsed_times) else None
        metadata = [
            FrameMetadata(source=str(path), time=parsed_times[i], header=self._headers[i], shape=shape)
            for i in range(len(self._frames))
        ]
        self._maps: dict[int, Any | None] = {}
        self.map_notice: str | None = None
        super().__init__(path, times, metadata, shape)

    def get_frame(self, index: int) -> np.ndarray:
        return self._frames[index]

    def get_map(self, index: int) -> Any | None:
        if index not in self._maps:
            result, notice, _ = make_solar_map(
                self._frames[index], self._headers[index], observation_time=self.get_time(index), prepare_aia=False
            )
            self._maps[index] = result
            self.map_notice = notice
        return self._maps[index]

    def get_wcs(self, index: int) -> WCS | None:
        smap = self.get_map(index)
        return smap.wcs if smap is not None else None

    def project_descriptor(self) -> dict[str, Any]:
        output = super().project_descriptor()
        output["variable"] = self.variable
        return output


def _field_names(value: Any) -> set[str]:
    array = np.asarray(value)
    return {str(name).lower() for name in (array.dtype.names or ())}


def _records(value: Any) -> list[Any]:
    array = np.asarray(value)
    if not array.dtype.names:
        return []
    return [array[()]] if array.ndim == 0 else list(array.reshape(-1))


def _field(record: Any, name: str, default: Any = None) -> Any:
    names = getattr(getattr(record, "dtype", None), "names", None) or ()
    lookup = {str(item).lower(): item for item in names}
    actual = lookup.get(name.lower())
    return record[actual] if actual is not None else default


def _scalar(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    array = np.asarray(value)
    while array.dtype == object and array.size == 1:
        array = np.asarray(array.reshape(-1)[0])
    if array.size != 1:
        return default
    item = array.reshape(-1)[0]
    if isinstance(item, bytes):
        return item.decode("utf-8", errors="replace").strip()
    return item.item() if hasattr(item, "item") else item


def _numeric_2d(value: Any) -> np.ndarray:
    array = np.asarray(value)
    while array.dtype == object and array.size == 1:
        array = np.asarray(array.reshape(-1)[0])
    array = np.squeeze(array)
    if array.ndim != 2 or not np.issubdtype(array.dtype, np.number):
        raise ValueError(f"SSW map DATA must be a numeric 2-D image; found {array.shape} {array.dtype}.")
    return np.asarray(array, dtype=float)


def _ssw_header(record: Any, shape: tuple[int, int]) -> tuple[dict[str, Any], Time | None]:
    """Translate documented SSW centre/scale tags to FITS helioprojective WCS."""
    ny, nx = shape
    raw_units = _scalar(_field(record, "xunits"), _scalar(_field(record, "units"), None))
    units = str(raw_units or "arcsec").lower()
    if units in {"arcsecs", "arcseconds", "arcsecond", "asec"}:
        units = "arcsec"
    angular = units in {"arcsec", "deg"}
    if not angular:
        units = "pixel"
    header: dict[str, Any] = {
        "CTYPE1": "HPLN-TAN" if angular else "LINEAR",
        "CTYPE2": "HPLT-TAN" if angular else "LINEAR",
        "CUNIT1": units,
        "CUNIT2": units,
        "CRPIX1": (nx + 1.0) / 2.0, "CRPIX2": (ny + 1.0) / 2.0,
        "CRVAL1": float(_scalar(_field(record, "xc"), 0.0)),
        "CRVAL2": float(_scalar(_field(record, "yc"), 0.0)),
        "CDELT1": float(_scalar(_field(record, "dx"), 1.0)),
        "CDELT2": float(_scalar(_field(record, "dy"), 1.0)),
        "CROTA2": float(_scalar(_field(record, "roll_angle"), _scalar(_field(record, "roll"), 0.0))),
    }
    obstime = _parse_ssw_time(_scalar(_field(record, "time")))
    if obstime is not None:
        header["DATE-OBS"] = obstime.utc.isot
    identifier = _scalar(_field(record, "id"))
    if identifier:
        header["INSTRUME"] = str(identifier)
    return header, obstime


def _parse_ssw_time(value: Any) -> Time | None:
    if value in (None, ""):
        return None
    try:
        from sunpy.time import parse_time
        return parse_time(str(value)).utc
    except Exception:
        try:
            return Time(str(value), scale="utc").utc
        except Exception:
            return None

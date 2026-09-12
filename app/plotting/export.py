"""Numerical and figure exports with source parameters retained."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from app.processing.td_generator import TDResult
from app.utils.exceptions import ExportError


def export_figure(
    figure: Any,
    path: str | Path,
    dpi: int = 300,
    transparent: bool = False,
    *,
    main_axes: Any | None = None,
    include_axes: bool = True,
    include_title: bool = True,
    include_colorbar: bool = True,
) -> None:
    """Write a Matplotlib figure with reversible publication-view filtering.

    Axes, title, and colorbar visibility are changed only while ``savefig`` is
    running and are restored even if a backend fails.  The live GUI therefore
    remains unchanged after exporting a stripped-down publication panel.
    """
    axes = main_axes or (figure.axes[0] if figure.axes else None)
    axis_was_on = bool(getattr(axes, "axison", True)) if axes is not None else True
    title_visible = axes.title.get_visible() if axes is not None else True
    auxiliary = [item for item in figure.axes if item is not axes]
    auxiliary_state = [
        (item, item.get_visible(), item.get_in_layout()) for item in auxiliary
    ]
    try:
        if axes is not None:
            if not include_axes:
                axes.set_axis_off()
            axes.title.set_visible(include_title and title_visible)
        if not include_colorbar:
            for item, _visible, _in_layout in auxiliary_state:
                item.set_visible(False)
                item.set_in_layout(False)
        figure.savefig(path, dpi=dpi, bbox_inches="tight", transparent=transparent)
    except Exception as exc:
        raise ExportError(f"无法将图像写入 {path}：{exc}") from exc
    finally:
        if axes is not None:
            axes.set_axis_on() if axis_was_on else axes.set_axis_off()
            axes.title.set_visible(title_visible)
        for item, visible, in_layout in auxiliary_state:
            item.set_visible(visible)
            item.set_in_layout(in_layout)
        if getattr(figure, "canvas", None) is not None:
            figure.canvas.draw_idle()


def export_td_npz(result: TDResult, path: str | Path) -> None:
    """Store arrays and JSON calculation state in a portable compressed NPZ."""
    np.savez_compressed(
        path,
        td=result.matrix,
        time_unix=result.times.unix if result.times is not None else np.array([], dtype=float),
        frame_indices=result.frame_indices,
        distance=result.distance,
        distance_unit=np.array(result.distance_unit),
        metadata_json=np.array(json.dumps(result.metadata)),
    )
    _write_sidecar(result, path)


def export_td_csv(result: TDResult, path: str | Path) -> None:
    """Export TD columns with explicit first rows for distance and time."""
    _export_td_delimited(result, path, ",")


def export_td_txt(result: TDResult, path: str | Path) -> None:
    """Export the same reproducible TD table as tab-delimited plain text."""
    _export_td_delimited(result, path, "\t")


def _export_td_delimited(result: TDResult, path: str | Path, delimiter: str) -> None:
    target = Path(path)
    header_time = (
        delimiter.join(result.times.isot)
        if result.times is not None
        else delimiter.join(map(str, result.frame_indices))
    )
    values = np.column_stack((result.distance, result.matrix))
    columns = f"distance[{result.distance_unit}]{delimiter}{header_time}"
    np.savetxt(target, values, delimiter=delimiter, header=columns, comments="")
    _write_sidecar(result, path)


def export_td_fits(result: TDResult, path: str | Path) -> None:
    """Export TD matrix plus TIME, DISTANCE, and JSON PATH/parameter HDUs."""
    primary = fits.PrimaryHDU(np.asarray(result.matrix, dtype=np.float64))
    primary.header["EXTNAME"] = "TIME_DISTANCE"
    primary.header["BUNIT"] = "arbitrary"
    primary.header["SOURCE"] = str(result.metadata.get("source", ""))[:68]
    primary.header["PATHTYPE"] = str(result.metadata["path"]["path_type"])[:68]
    primary.header["PATHWID"] = float(result.metadata["path"]["width"])
    primary.header["WIDUNIT"] = str(result.metadata["path"]["width_unit"])[:16]
    primary.header["DISTUNIT"] = result.distance_unit[:16]
    primary.header["INTEG"] = str(result.metadata["path"]["integration_method"])[:16]
    primary.header["INTERP"] = str(result.metadata["path"]["interpolation"])[:16]
    primary.header["TDORDER"] = "DIST,TIME"
    time_values = result.times.unix if result.times is not None else result.frame_indices.astype(float)
    time_format = "UNIX seconds" if result.times is not None else "frame index"
    time_hdu = fits.BinTableHDU.from_columns(
        [fits.Column(name="TIME", format="D", unit=time_format, array=time_values)], name="TIME"
    )
    distance_hdu = fits.BinTableHDU.from_columns(
        [fits.Column(name="DISTANCE", format="D", unit=result.distance_unit, array=result.distance)],
        name="DISTANCE",
    )
    parameter_hdu = fits.BinTableHDU.from_columns(
        [fits.Column(name="JSON", format=f"{max(1, len(json.dumps(result.metadata)))}A",
                     array=[json.dumps(result.metadata)])],
        name="PARAMETERS",
    )
    fits.HDUList([primary, time_hdu, distance_hdu, parameter_hdu]).writeto(path, overwrite=True)
    _write_sidecar(result, path)


def _write_sidecar(result: TDResult, target: str | Path) -> None:
    """Write reproducibility parameters next to an exported numerical result."""
    destination = Path(target).with_suffix(".result.json")
    destination.write_text(json.dumps(result.metadata, indent=2), encoding="utf-8")

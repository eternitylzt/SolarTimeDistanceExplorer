"""Export aggregated closed-region trends and histogram bins."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
from astropy.io import fits

from app.processing.region_analysis import RegionHistogramResult, RegionTrendResult
from app.processing.provenance import write_sidecar


def export_region_result(result: RegionTrendResult | RegionHistogramResult, destination: str | Path) -> None:
    path = Path(destination); suffix = path.suffix.lower()
    if suffix == ".sav":
        raise ValueError(
            "SciPy 可以读取 IDL SAVE 文件，但没有符合标准的 writesav 写入接口。"
            "请导出为 FITS/CSV/TXT；这些格式无需 IDL 即可完整保存数值结果。"
        )
    if suffix in {".fits", ".fit", ".fts"}:
        _export_fits(result, path)
    elif suffix == ".csv":
        _export_text(result, path, ",")
    elif suffix in {".txt", ".dat"}:
        _export_text(result, path, "\t")
    else:
        raise ValueError("区域数据请选择 .fits、.csv 或 .txt 格式导出。")
    write_sidecar(path, {**result.metadata, "region_names": result.region_names,
        "valid_counts": result.valid_counts, "mask_counts": result.mask_counts,
        "frame_index": getattr(result, "frame_index", None),
        "observation_time_utc": result.time.utc.isot if isinstance(result, RegionHistogramResult) and result.time is not None else None})


def _export_fits(result, path: Path) -> None:
    if isinstance(result, RegionTrendResult):
        primary = fits.PrimaryHDU(np.asarray(result.values, dtype=float))
        primary.header["PRODUCT"] = "REGION_TREND"; primary.header["STAT"] = result.statistic
        hdus = [primary]
        for name, array in (("VALID_COUNT", result.valid_counts), ("MASK_COUNT", result.mask_counts),
                            ("AREA_ARCSEC2", result.valid_area_arcsec2)):
            if array is not None:
                hdus.append(fits.ImageHDU(array, name=name))
        encoded = json.dumps(result.metadata)
        hdus.append(fits.BinTableHDU.from_columns([fits.Column(name="JSON", format=f"{max(1,len(encoded))}A", array=[encoded])], name="PARAMETERS"))
        time_values = result.times.utc.mjd if result.times is not None else result.frame_indices.astype(float)
        hdus.append(fits.BinTableHDU.from_columns([fits.Column(name="TIME_MJD" if result.times is not None else "FRAME", format="D", array=time_values)], name="TIME"))
        max_len = max(len(name) for name in result.region_names)
        hdus.append(fits.BinTableHDU.from_columns([fits.Column(name="NAME", format=f"{max_len}A", array=result.region_names)], name="REGIONS"))
        fits.HDUList(hdus).writeto(path, overwrite=True); return
    hdus = [fits.PrimaryHDU()]
    encoded = json.dumps(result.metadata)
    hdus.append(fits.BinTableHDU.from_columns([fits.Column(name="JSON",format=f"{max(1,len(encoded))}A",array=[encoded])],name="PARAMETERS"))
    for index, (name, edges, counts) in enumerate(zip(result.region_names, result.edges, result.counts, strict=True)):
        table = fits.BinTableHDU.from_columns([
            fits.Column(name="BIN_LEFT", format="D", array=edges[:-1]),
            fits.Column(name="BIN_RIGHT", format="D", array=edges[1:]),
            fits.Column(name="COUNT", format="K", array=counts),
            fits.Column(name="FREQUENCY", format="D", array=counts/max(1,int(np.sum(counts)))),
        ], name=f"HIST{index+1}")
        table.header["REGION"] = name; table.header["FRAME"] = result.frame_index
        if result.valid_counts is not None:
            table.header["NVALID"] = int(result.valid_counts[index])
        if result.mask_counts is not None:
            table.header["NMASK"] = int(result.mask_counts[index])
        if result.time is not None:
            table.header["DATE-OBS"] = result.time.utc.isot
        hdus.append(table)
    fits.HDUList(hdus).writeto(path, overwrite=True)


def _export_text(result, path: Path, delimiter: str) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, delimiter=delimiter)
        if isinstance(result, RegionTrendResult):
            coverage_sets = [(suffix, array) for suffix,array in (("valid_pixels",result.valid_counts),("mask_pixels",result.mask_counts),("area_arcsec2",result.valid_area_arcsec2)) if array is not None]
            coverage_labels = [f"{name}_{suffix}" for suffix,_ in coverage_sets for name in result.region_names]
            writer.writerow(["time_utc" if result.times is not None else "frame", *result.region_names, *coverage_labels])
            for index in range(len(result.frame_indices)):
                coordinate = result.times[index].utc.isot if result.times is not None else int(result.frame_indices[index])
                coverage = [v for _,array in coverage_sets for v in array[:,index]]
                writer.writerow([coordinate, *result.values[:, index], *coverage])
        else:
            if result.time is not None:
                writer.writerow(["observation_time_utc", result.time.utc.isot])
            writer.writerow(["region", "bin_left", "bin_right", "count", "relative_frequency"])
            for name, edges, counts in zip(result.region_names, result.edges, result.counts, strict=True):
                for left, right, count in zip(edges[:-1], edges[1:], counts, strict=True):
                    writer.writerow([name, left, right, int(count), float(count)/max(1,int(np.sum(counts)))])

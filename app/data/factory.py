"""Reopen data sources described in saved project JSON."""

from __future__ import annotations

from typing import Any

from app.data.base import TimeSeriesDataset
from app.data.fits_cube import FitsCubeDataset
from app.data.fits_folder import FitsFolderDataset
from app.data.fits_image import FitsImageDataset
from app.data.sav_cube import SavCubeDataset, SavImageDataset, SavMapDataset


def open_from_descriptor(descriptor: dict[str, Any]) -> TimeSeriesDataset:
    """Instantiate a dataset from a project descriptor after path existence checks."""
    source_type = descriptor["source_type"]
    source = descriptor["source"]
    if source_type == "fits_folder":
        return FitsFolderDataset(
            source,
            int(descriptor.get("cache_size", 12)),
            bool(descriptor.get("prepare_aia", True)),
        )
    if source_type == "fits_image":
        return FitsImageDataset(source, bool(descriptor.get("prepare_aia", True)))
    if source_type == "fits_cube":
        return FitsCubeDataset(source, int(descriptor["time_axis"]))
    if source_type == "sav_cube":
        return SavCubeDataset(
            source,
            descriptor["variable"],
            int(descriptor["time_axis"]),
            descriptor.get("time_variable"),
        )
    if source_type == "sav_image":
        return SavImageDataset(source, descriptor["variable"])
    if source_type == "sav_ssw_map":
        return SavMapDataset(source, descriptor["variable"])
    raise ValueError(f"Unsupported project source type: {source_type}")

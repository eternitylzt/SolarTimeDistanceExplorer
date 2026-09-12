"""Cancellable numerical time-distance engine independent of Qt widgets."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from astropy.time import Time
from astropy.wcs import WCS

from app.data.base import TimeSeriesDataset
from app.paths.base import PathGeometry
from app.paths.geometry import sample_path_geometry
from app.paths.sampling import sample_path_width
from app.processing.preprocessing import FrameProcessor, IdentityProcessor
from app.utils.units import convert_width_to_pixels, distance_along_path, pixel_scale_arcsec
from app.processing.provenance import result_provenance
from app.version import __version__


@dataclass(frozen=True)
class TDConfig:
    """Explicit calculation inputs; TD always has shape distance by time."""

    distance_unit: str = "pixel"
    tracking_mode: str = "pixel_fixed"
    normalize_exposure: bool = False
    use_full_resolution: bool = True


@dataclass
class TDResult:
    """Numerical TD product and reproducibility metadata."""

    matrix: np.ndarray
    times: Time | None
    frame_indices: np.ndarray
    distance: np.ndarray
    distance_unit: str
    path_id: str
    metadata: dict[str, Any]

    @property
    def shape(self) -> tuple[int, int]:
        """Return (distance samples, time samples)."""
        return self.matrix.shape


def generate_time_distance(
    dataset: TimeSeriesDataset,
    path: PathGeometry,
    config: TDConfig | None = None,
    processor: FrameProcessor | None = None,
    progress: Callable[[int, int], None] | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> TDResult:
    """Compute TD[distance, time] with WCS-aware, finite-width extraction.

    For each observed frame, the function obtains the path in that frame. World
    tracking transforms saved reference world samples through that frame's WCS;
    pixel tracking preserves fixed reference pixels. Every extraction uses SciPy
    sub-pixel interpolation and a local-normal scientific slit width. Frames may
    be irregularly timed; timestamps are retained rather than resampled.
    """
    if not path.complete:
        raise ValueError("Select and finish a path before generating a TD diagram.")
    config = config or TDConfig(tracking_mode=path.tracking_mode)
    processor = processor or IdentityProcessor()

    reference_wcs = dataset.get_wcs(0)
    reference_samples, _ = sample_path_geometry(path)
    if path.coordinate_mode == "world" and path.world_sample_values is None:
        if reference_wcs is None:
            raise ValueError("World-coordinate mode needs a valid WCS in the reference frame.")
        path.capture_world_samples(reference_wcs, reference_samples)
    try:
        distance = distance_along_path(reference_samples, config.distance_unit, reference_wcs)
    except ValueError:
        # Pixel is safe; more physical units must never be fabricated.
        if config.distance_unit != "pixel":
            raise
        distance = distance_along_path(reference_samples, "pixel", reference_wcs)

    output = np.full((len(reference_samples), dataset.n_frames), np.nan, dtype=float)
    for index in range(dataset.n_frames):
        if cancelled and cancelled():
            raise InterruptedError("Time-distance generation cancelled by user.")
        frame = dataset.get_frame(index)
        header = dict(dataset.get_header(index))
        frame = processor.process(frame, header)

        samples = reference_samples
        if config.tracking_mode == "world_fixed" or path.tracking_mode == "world_fixed":
            transformed = path.pixel_samples_for_wcs(dataset.get_wcs(index))
            if transformed is None:
                raise ValueError(
                    f"Frame {index} cannot transform the selected world-coordinate path. "
                    "Use Pixel fixed mode or repair the frame WCS."
                )
            samples = transformed
        elif config.tracking_mode == "solar_rotation":
            # Deliberately honest: no silent solar-rotation coordinate mutation.
            raise NotImplementedError(
                "Solar-rotation tracking is experimental in this release. Use World-coordinate fixed."
            )

        width_pixel = convert_width_to_pixels(path.width, path.width_unit, dataset.get_wcs(index))
        values = sample_path_width(
            frame,
            samples,
            width_pixel,
            integration=path.integration_method,
            interpolation=path.interpolation,
        )
        if config.normalize_exposure:
            exposure = dataset.get_frame_metadata(index).exposure_seconds
            if exposure is None:
                raise ValueError(f"Frame {index} has no usable exposure time for normalization.")
            values = values / exposure
        output[:, index] = values
        if progress:
            progress(index + 1, dataset.n_frames)

    return TDResult(
        matrix=output,
        times=dataset.times,
        frame_indices=np.arange(dataset.n_frames),
        distance=distance,
        distance_unit=config.distance_unit,
        path_id=path.id,
        metadata={
            "source": str(dataset.source),
            "source_type": dataset.source_type,
            "path": path.to_dict(),
            "config": asdict(config),
            "reference_pixel_scale_arcsec": pixel_scale_arcsec(reference_wcs),
            "matrix_convention": "TD[distance_index, time_index]",
            "software": f"Solar Time-Distance Explorer {__version__}",
            "provenance": result_provenance(dataset, {"path": path.to_dict(), "config": asdict(config)}),
        },
    )

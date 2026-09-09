"""Standards-compatible movie export through the bundled FFmpeg executable."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

import numpy as np
from matplotlib import colormaps
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import Normalize
from matplotlib.figure import Figure
from PIL import Image

from app.data.base import TimeSeriesDataset
from app.paths.base import PathGeometry
from app.paths.geometry import sample_path_geometry
from app.plotting.normalization import make_norm
from app.regions.base import RegionGeometry
from app.utils.exceptions import ExportError


def _render_frame(frame: np.ndarray, cmap_name: str, norm: Normalize) -> np.ndarray:
    """Map scalar image values to RGB pixels for a deterministic video encoder."""
    array = np.asarray(frame, dtype=float)
    rgba = colormaps[cmap_name](norm(array), bytes=True)
    # MP4 has no alpha channel. Render invalid values as black explicitly so
    # conversion to YUV does not depend on a writer-specific alpha policy.
    rgba[~np.isfinite(array)] = (0, 0, 0, 255)
    return np.ascontiguousarray(rgba[..., :3])


def _path_points_for_frame(geometry: PathGeometry, wcs: object | None) -> np.ndarray:
    """Return the visible centreline in this frame's pixel coordinate system."""
    transformed = geometry.pixel_samples_for_wcs(wcs)  # type: ignore[arg-type]
    if transformed is not None:
        return transformed
    points, _ = sample_path_geometry(geometry)
    return points


def _render_scientific_frame(
    dataset: TimeSeriesDataset,
    index: int,
    frame: np.ndarray,
    cmap_name: str,
    norm: Normalize,
    output_size: tuple[int, int],
    viewport_limits: tuple[tuple[float, float], tuple[float, float]] | None,
    *,
    include_axes: bool,
    include_timestamp: bool,
    include_title: bool,
    include_colorbar: bool,
    paths: Sequence[PathGeometry],
    regions: Sequence[RegionGeometry],
) -> np.ndarray:
    """Render one publication-style frame with optional WCS and annotations.

    The selected viewport is expressed in full-resolution pixel coordinates,
    exactly like Matplotlib's interactive image axes. A per-frame WCS projection
    keeps solar coordinate ticks correct when pointing metadata changes.
    """
    width, height = max(16, int(output_size[0])), max(16, int(output_size[1]))
    dpi = 100.0
    figure = Figure(figsize=(width / dpi, height / dpi), dpi=dpi, layout="constrained")
    FigureCanvasAgg(figure)
    solar_map = dataset.get_map(index)
    wcs = solar_map.wcs if solar_map is not None else dataset.get_wcs(index)
    try:
        axes = figure.add_subplot(111, projection=solar_map if solar_map is not None else wcs)
    except Exception:
        axes = figure.add_subplot(111)
        wcs = None
    image = axes.imshow(
        np.asarray(frame), origin="lower", cmap=cmap_name, norm=norm,
        interpolation="nearest",
        extent=(-0.5, frame.shape[1] - 0.5, -0.5, frame.shape[0] - 0.5),
    )
    if viewport_limits is not None:
        axes.set_xlim(*viewport_limits[0])
        axes.set_ylim(*viewport_limits[1])
    else:
        axes.set_xlim(-0.5, frame.shape[1] - 0.5)
        axes.set_ylim(-0.5, frame.shape[0] - 0.5)

    if include_axes:
        if wcs is not None and getattr(wcs, "has_celestial", False) and hasattr(axes, "coords"):
            try:
                axes.coords[0].set_axislabel("Solar-X [arcsec]")
                axes.coords[1].set_axislabel("Solar-Y [arcsec]")
                axes.coords.grid(color="white", alpha=0.18, linestyle=":")
            except Exception:
                axes.set_xlabel("X [pixel]")
                axes.set_ylabel("Y [pixel]")
        else:
            axes.set_xlabel("X [pixel]")
            axes.set_ylabel("Y [pixel]")
    else:
        axes.set_axis_off()

    time = dataset.get_time(index)
    time_text = time.utc.isot if time is not None else f"Frame {index + 1}"
    if include_title:
        axes.set_title("Solar Map" if wcs is not None else "Image Sequence")
    if include_timestamp:
        axes.text(
            0.015, 0.985, time_text, transform=axes.transAxes,
            ha="left", va="top", color="white", fontsize=10, zorder=50,
            bbox={"facecolor": "black", "alpha": 0.62, "edgecolor": "none", "pad": 2.5},
        )

    for geometry in paths:
        if not geometry.visible or not geometry.complete:
            continue
        try:
            points = _path_points_for_frame(geometry, wcs)
            axes.plot(
                points[:, 0], points[:, 1], color=geometry.display_color,
                linewidth=geometry.display_linewidth,
                linestyle=geometry.display_linestyle, alpha=geometry.display_alpha,
                zorder=30,
            )
            if geometry.show_label:
                position = geometry.label_position_pixel or (
                    float(points[0, 0] + 5.0), float(points[0, 1] + 5.0)
                )
                axes.text(
                    position[0], position[1], geometry.name,
                    color=geometry.label_color, fontsize=geometry.label_fontsize,
                    fontweight="bold", zorder=31,
                    bbox={"facecolor": geometry.label_background_color, "alpha": 0.65,
                          "edgecolor": "none", "pad": 1.5},
                )
        except Exception:
            continue
    for geometry in regions:
        if not geometry.visible or not geometry.complete:
            continue
        try:
            outline = geometry.outline_for_wcs(wcs)  # type: ignore[arg-type]
            axes.plot(
                outline[:, 0], outline[:, 1], color=geometry.display_color,
                linewidth=geometry.display_linewidth, alpha=geometry.display_alpha,
                zorder=30,
            )
            if geometry.show_label:
                position = geometry.label_position_pixel or (
                    float(outline[0, 0] + 5.0), float(outline[0, 1] + 5.0)
                )
                axes.text(
                    position[0], position[1], geometry.name,
                    color=geometry.label_color, fontsize=geometry.label_fontsize,
                    fontweight="bold", zorder=31,
                    bbox={"facecolor": geometry.label_background_color, "alpha": 0.65,
                          "edgecolor": "none", "pad": 1.5},
                )
        except Exception:
            continue
    if include_colorbar:
        colorbar = figure.colorbar(image, ax=axes, pad=0.02)
        colorbar.set_label("Intensity")

    figure.canvas.draw()
    rgba = np.asarray(figure.canvas.buffer_rgba())
    return np.ascontiguousarray(rgba[..., :3])


def _resize_frame(frame: np.ndarray, output_size: tuple[int, int] | None) -> np.ndarray:
    if output_size is None or (frame.shape[1], frame.shape[0]) == output_size:
        return frame
    image = Image.fromarray(frame).resize(output_size, Image.Resampling.LANCZOS)
    return np.asarray(image)


def _pad_even(frame: np.ndarray) -> np.ndarray:
    """Pad odd dimensions for broadly supported yuv420p H.264 playback."""
    pad_height = frame.shape[0] % 2
    pad_width = frame.shape[1] % 2
    if not pad_height and not pad_width:
        return frame
    return np.pad(frame, ((0, pad_height), (0, pad_width), (0, 0)), mode="edge")


def _ffmpeg_executable() -> Path:
    try:
        import imageio_ffmpeg

        executable = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as exc:
        raise ExportError(f"无法加载随程序提供的 FFmpeg 编码器：{exc}") from exc
    if not executable.is_file():
        raise ExportError("未找到随程序提供的 FFmpeg 编码器。")
    return executable


def _run_ffmpeg(command: list[str]) -> None:
    completed = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        detail = " ".join((completed.stderr or completed.stdout).split())[-1800:]
        raise ExportError(f"FFmpeg 编码失败：{detail or 'unknown encoder error'}")


def _verify_video(ffmpeg: Path, target: Path) -> None:
    """Decode one output frame before reporting success to the user."""
    completed = subprocess.run(
        [
            str(ffmpeg), "-v", "error", "-i", str(target), "-map", "0:v:0",
            "-frames:v", "1", "-f", "null", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    if completed.returncode != 0:
        raise ExportError(f"导出文件无法解码：{completed.stderr.strip()[-1200:]}")


def export_animation(
    dataset: TimeSeriesDataset,
    path: str | Path,
    start: int,
    end: int,
    step: int,
    fps: float,
    cmap: str,
    normalization_mode: str = "percentile",
    fixed_normalization: bool = True,
    progress: Callable[[int, int], None] | None = None,
    output_size: tuple[int, int] | None = None,
    codec: str = "libx264",
    bitrate: str = "8M",
    low_percent: float = 1.0,
    high_percent: float = 99.0,
    stretch: str = "linear",
    vmin: float | None = None,
    vmax: float | None = None,
    viewport_limits: tuple[tuple[float, float], tuple[float, float]] | None = None,
    include_axes: bool = False,
    include_timestamp: bool = False,
    include_title: bool = False,
    include_colorbar: bool = False,
    paths: Sequence[PathGeometry] | None = None,
    regions: Sequence[RegionGeometry] | None = None,
) -> None:
    """Export GIF/MP4/AVI from equal-size PNG frames, then verify decoding.

    MP4 uses H.264, yuv420p, even dimensions and a fast-start index. This is
    intentionally stricter than the former generic imageio writer and is
    compatible with Windows Media Player, VLC, browsers and presentation apps.
    """
    target = Path(path).resolve()
    suffix = target.suffix.lower()
    if suffix not in {".gif", ".mp4", ".avi"}:
        raise ExportError("动画导出请选择 .gif、.mp4 或 .avi。")
    if fps <= 0:
        raise ExportError("帧率必须大于 0。")
    indices = list(range(start, end + 1, max(1, step)))
    if not indices:
        raise ExportError("动画帧范围为空。")

    target.parent.mkdir(parents=True, exist_ok=True)
    first = dataset.get_frame(indices[0])
    fixed_norm = make_norm(
        first, normalization_mode, stretch=stretch, vmin=vmin, vmax=vmax,
        low_percent=low_percent, high_percent=high_percent,
    )
    ffmpeg = _ffmpeg_executable()
    staging = Path(tempfile.mkdtemp(prefix=".stde_movie_", dir=target.parent))
    encoded = staging / f"encoded{suffix}"
    try:
        for count, index in enumerate(indices, start=1):
            frame = dataset.get_frame(index)
            norm = fixed_norm if fixed_normalization else make_norm(
                frame,
                normalization_mode,
                stretch=stretch,
                vmin=vmin,
                vmax=vmax,
                low_percent=low_percent,
                high_percent=high_percent,
            )
            scientific_render = bool(
                viewport_limits is not None or include_axes or include_timestamp
                or include_title or include_colorbar or paths or regions
            )
            if scientific_render:
                render_size = output_size or (int(frame.shape[1]), int(frame.shape[0]))
                rgb = _render_scientific_frame(
                    dataset, index, frame, cmap, norm, render_size, viewport_limits,
                    include_axes=include_axes,
                    include_timestamp=include_timestamp,
                    include_title=include_title,
                    include_colorbar=include_colorbar,
                    paths=paths or (), regions=regions or (),
                )
            else:
                rgb = _resize_frame(_render_frame(frame, cmap, norm), output_size)
            if suffix in {".mp4", ".avi"}:
                rgb = _pad_even(rgb)
            Image.fromarray(rgb).save(staging / f"frame_{count - 1:06d}.png", "PNG")
            if progress:
                progress(count, len(indices) + 1)

        command = [
            str(ffmpeg), "-y", "-hide_banner", "-loglevel", "error",
            "-framerate", f"{fps:g}", "-start_number", "0",
            "-i", str(staging / "frame_%06d.png"),
        ]
        if suffix == ".mp4":
            chosen_codec = codec if codec in {"libx264", "mpeg4"} else "libx264"
            command.extend([
                "-c:v", chosen_codec, "-pix_fmt", "yuv420p",
                "-b:v", bitrate or "8M", "-movflags", "+faststart",
            ])
        elif suffix == ".avi":
            command.extend(["-c:v", "mpeg4", "-pix_fmt", "yuv420p", "-b:v", bitrate or "8M"])
        else:
            command.extend([
                "-filter_complex",
                "split[s0][s1];[s0]palettegen=max_colors=256[p];"
                "[s1][p]paletteuse=dither=sierra2_4a",
                "-loop", "0",
            ])
        command.append(str(encoded))
        _run_ffmpeg(command)
        if not encoded.is_file() or encoded.stat().st_size == 0:
            raise ExportError("编码器没有生成有效的视频文件。")
        _verify_video(ffmpeg, encoded)
        os.replace(encoded, target)
        if progress:
            progress(len(indices) + 1, len(indices) + 1)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(f"动画导出失败：{exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)

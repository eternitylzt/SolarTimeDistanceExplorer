"""Interactive Matplotlib image canvas, including WCS axes and path overlays."""

from __future__ import annotations

from typing import Any

import numpy as np
from astropy import units as u
from astropy.wcs import WCS
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy

from app.paths.base import PathGeometry
from app.regions.base import RegionGeometry
from app.paths.geometry import sample_path_geometry
from app.paths.sampling import width_boundaries
from app.plotting.normalization import make_norm
from app.utils.units import convert_width_to_pixels


class ImageCanvas(FigureCanvasQTAgg):
    """Matplotlib canvas for raw images, coordinate labels, and editable paths."""

    cursor_changed = Signal(object)
    mouse_pressed = Signal(object)
    mouse_moved = Signal(object)
    mouse_released = Signal(object)

    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 7), layout="constrained")
        layout_engine = self.figure.get_layout_engine()
        if layout_engine is not None:
            layout_engine.set(w_pad=8.0 / 72.0, h_pad=5.0 / 72.0, wspace=0.04, hspace=0.04)
        super().__init__(self.figure)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.axes = self.figure.add_subplot(111)
        self.frame: np.ndarray | None = None
        self.wcs: WCS | None = None
        self.solar_map: Any | None = None
        self.current_path: PathGeometry | None = None
        self.paths: list[PathGeometry] = []
        self._path_artists: list[Any] = []
        self._image_artist: Any | None = None
        self._colorbar: Any | None = None
        self._preview_data: np.ndarray | None = None
        self.regions: list[RegionGeometry] = []
        self.active_region_id: str | None = None
        self._region_preview: tuple[RegionGeometry, tuple[float, float] | None] | None = None
        self._region_artists: list[Any] = []
        self.mpl_connect("motion_notify_event", self._on_motion)
        self.mpl_connect("button_press_event", self._on_press)
        self.mpl_connect("button_release_event", self._on_release)

    def show_frame(
        self,
        frame: np.ndarray,
        wcs: WCS | None,
        title: str,
        cmap: str = "gray",
        normalization_mode: str = "percentile",
        stretch: str = "linear",
        vmin: float | None = None,
        vmax: float | None = None,
        low_percent: float = 1.0,
        high_percent: float = 99.0,
        fixed_norm: Any | None = None,
        solar_map: Any | None = None,
    ) -> Any:
        """Render a frame with SunPy Map/WCSAxes when solar metadata is valid."""
        self.frame = np.asarray(frame)
        stride = max(1, int(np.ceil(max(self.frame.shape) / 1600.0)))
        self._preview_data = self.frame[::stride, ::stride]
        self.solar_map = solar_map
        self.wcs = solar_map.wcs if solar_map is not None else wcs
        use_wcs_axes = bool(self.wcs is not None and self.wcs.has_celestial)
        can_reuse = (
            self._image_artist is not None
            and ((use_wcs_axes and hasattr(self.axes, "reset_wcs"))
                 or (not use_wcs_axes and not hasattr(self.axes, "reset_wcs")))
        )
        norm = fixed_norm or make_norm(
            self.frame,
            mode=normalization_mode,
            stretch=stretch,
            vmin=vmin,
            vmax=vmax,
            low_percent=low_percent,
            high_percent=high_percent,
        )
        if can_reuse:
            # Keep the user's interactive pan/zoom selection while stepping or
            # playing frames. set_extent()/reset_wcs() otherwise restores the
            # full image on every frame and makes "export current view" useless.
            visible_xlim = self.axes.get_xlim()
            visible_ylim = self.axes.get_ylim()
            if use_wcs_axes:
                self.axes.reset_wcs(wcs=self.wcs)
                self.axes.coords.grid(color="white", alpha=0.18, linestyle=":")
                self.axes.coords[0].set_axislabel("Solar-X [arcsec]")
                self.axes.coords[1].set_axislabel("Solar-Y [arcsec]")
            self._image_artist.set_data(self._preview_data)
            self._image_artist.set_extent(
                (-0.5, self.frame.shape[1] - 0.5, -0.5, self.frame.shape[0] - 0.5)
            )
            self._image_artist.set_cmap(cmap)
            self._image_artist.set_norm(norm)
            self.axes.set_title(title)
            self.axes.set_xlim(*visible_xlim)
            self.axes.set_ylim(*visible_ylim)
            if self._colorbar is not None:
                self._colorbar.update_normal(self._image_artist)
            self._draw_paths()
            self._draw_regions()
            self.draw_idle()
            return norm

        self.figure.clear()
        if solar_map is not None:
            # This is the Python analogue of SSW fits2map/plot_map: SunPy's
            # projection carries the helioprojective frame, observer and rsun
            # metadata into Matplotlib WCSAxes.
            self.axes = self.figure.add_subplot(111, projection=solar_map)
            self.axes.coords.grid(color="white", alpha=0.18, linestyle=":")
        elif self.wcs is not None and self.wcs.has_celestial:
            self.axes = self.figure.add_subplot(111, projection=self.wcs)
            self.axes.coords.grid(color="white", alpha=0.18, linestyle=":")
        else:
            self.axes = self.figure.add_subplot(111)
            self.axes.set_xlabel("X [pixel]")
            self.axes.set_ylabel("Y [pixel]")
        self.axes.set_anchor("C")
        # The preview array is decimated for responsive AIA interaction, but
        # extent remains in original full-resolution pixel coordinates. Thus
        # mouse-selected slits/regions and WCSAxes ticks remain scientifically
        # correct. TD calculations continue to use self.frame/source data.
        self._image_artist = self.axes.imshow(
            self._preview_data,
            origin="lower",
            cmap=cmap,
            norm=norm,
            interpolation="nearest",
            extent=(-0.5, self.frame.shape[1] - 0.5, -0.5, self.frame.shape[0] - 0.5),
        )
        if solar_map is not None:
            try:
                self.axes.coords[0].set_axislabel("Solar-X [arcsec]")
                self.axes.coords[1].set_axislabel("Solar-Y [arcsec]")
            except Exception:
                pass
        self.axes.set_title(title)
        self._colorbar = self.figure.colorbar(
            self._image_artist, ax=self.axes, pad=0.035, fraction=0.05, shrink=0.92
        )
        self._colorbar.set_label("Intensity", labelpad=8)
        # Figure.colorbar() changes the parent axes anchor to the east. Reset it
        # after colorbar creation so the scientific image remains centered in
        # the available canvas instead of appearing right-aligned.
        self.axes.set_anchor("C")
        self._path_artists = []
        self._region_artists = []
        self._draw_paths()
        self._draw_regions()
        self.draw_idle()
        return norm

    def set_full_resolution_display(self, enabled: bool) -> None:
        """Temporarily switch artist data for publication export without changing coordinates."""
        if self._image_artist is None or self.frame is None:
            return
        self._image_artist.set_data(self.frame if enabled else self._preview_data)
        self.draw()

    def update_display(
        self,
        cmap: str,
        normalization_mode: str,
        stretch: str,
        vmin: float | None,
        vmax: float | None,
        low_percent: float = 1.0,
        high_percent: float = 99.0,
        fixed_norm: Any | None = None,
    ) -> Any | None:
        """Update colour mapping without rebuilding WCSAxes or rereading a frame."""
        if self.frame is None or self._image_artist is None:
            return None
        norm = fixed_norm or make_norm(
            self.frame,
            mode=normalization_mode,
            stretch=stretch,
            vmin=vmin,
            vmax=vmax,
            low_percent=low_percent,
            high_percent=high_percent,
        )
        self._image_artist.set_cmap(cmap)
        self._image_artist.set_norm(norm)
        if self._colorbar is not None:
            self._colorbar.update_normal(self._image_artist)
        self.draw_idle()
        return norm

    def set_path(self, geometry: PathGeometry | None) -> None:
        """Set active path and redraw centerline/control handles without data mutation."""
        self.current_path = geometry
        if geometry is not None:
            for index, item in enumerate(self.paths):
                if item.id == geometry.id:
                    self.paths[index] = geometry
                    break
            else:
                self.paths.append(geometry)
        self._draw_paths()
        self.draw_idle()

    def set_paths(self, paths: list[PathGeometry], active_id: str | None = None) -> None:
        """Display any number of named slits while editing only the active one."""
        self.paths = list(paths)
        self.current_path = next((item for item in paths if item.id == active_id), None)
        self._draw_paths()
        self.draw_idle()

    def set_regions(self, regions: list[RegionGeometry], active_id: str | None = None) -> None:
        """Display all closed analysis regions without modifying image data."""
        self.regions = regions
        self.active_region_id = active_id
        self._draw_regions()
        self.draw_idle()

    def set_region_preview(
        self, geometry: RegionGeometry | None, point: tuple[float, float] | None
    ) -> None:
        self._region_preview = (geometry, point) if geometry is not None else None
        self._draw_regions()
        self.draw_idle()

    def _clear_region_artists(self) -> None:
        for artist in self._region_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError):
                pass
        self._region_artists.clear()

    def _draw_regions(self) -> None:
        self._clear_region_artists()
        if self.axes is None:
            return
        preview_geometry = self._region_preview[0] if self._region_preview else None
        for geometry in self.regions:
            if not geometry.visible:
                continue
            preview = self._region_preview[1] if geometry is preview_geometry and self._region_preview else None
            outline = geometry.outline_points(preview)
            if len(outline) >= 2:
                self._region_artists.extend(
                    self.axes.plot(
                        outline[:, 0], outline[:, 1], color=geometry.display_color,
                        linewidth=geometry.display_linewidth, alpha=geometry.display_alpha,
                        linestyle="--" if preview is not None else "-", zorder=21,
                    )
                )
            if geometry.id == self.active_region_id or geometry is preview_geometry:
                points = geometry.control_points_pixel
                if len(points):
                    self._region_artists.extend(
                        self.axes.plot(points[:, 0], points[:, 1], "s", color=geometry.display_color,
                                       markeredgecolor="black", markersize=6, zorder=22)
                    )
            if geometry.show_label and geometry.complete:
                position = geometry.label_position_pixel
                if position is None:
                    outline = geometry.outline_points()
                    position = (float(outline[0, 0] + 5.0), float(outline[0, 1] + 5.0))
                self._region_artists.append(
                    self.axes.text(
                        position[0], position[1], geometry.name, color=geometry.label_color,
                        fontsize=geometry.label_fontsize, fontweight="bold", zorder=23,
                        bbox={"facecolor": geometry.label_background_color, "alpha": 0.65, "edgecolor": "none", "pad": 1.5},
                    )
                )

    def _clear_path_artists(self) -> None:
        for artist in self._path_artists:
            try:
                artist.remove()
            except (ValueError, AttributeError):
                pass
        self._path_artists.clear()

    def _draw_paths(self) -> None:
        self._clear_path_artists()
        if self.axes is None:
            return
        for geometry in self.paths:
            if geometry.visible:
                self._draw_one_path(geometry, geometry is self.current_path)

    def _draw_one_path(self, geometry: PathGeometry, active: bool) -> None:
        """Draw one scientific slit; its GUI stroke is independent of slit width."""
        points = geometry.control_points_pixel
        if len(points) and active:
            controls = self.axes.plot(
                points[:, 0],
                points[:, 1],
                "o",
                color=geometry.display_color,
                markeredgecolor="black",
                markersize=6,
                alpha=geometry.display_alpha,
                zorder=20,
            )
            self._path_artists.extend(controls)
        if not geometry.complete:
            return
        try:
            samples, _ = sample_path_geometry(geometry)
        except ValueError:
            return
        line = self.axes.plot(
            samples[:, 0],
            samples[:, 1],
            color=geometry.display_color,
            linewidth=geometry.display_linewidth,
            linestyle=geometry.display_linestyle,
            alpha=geometry.display_alpha,
            zorder=19,
        )
        self._path_artists.extend(line)
        if geometry.show_label:
            position = geometry.label_position_pixel
            if position is None:
                position = (float(samples[0, 0] + 5.0), float(samples[0, 1] + 5.0))
            self._path_artists.append(
                self.axes.text(
                    position[0], position[1], geometry.name, color=geometry.label_color,
                    fontsize=geometry.label_fontsize, fontweight="bold", zorder=22,
                    bbox={"facecolor": geometry.label_background_color, "alpha": 0.65, "edgecolor": "none", "pad": 1.5},
                )
            )
        if geometry.show_width_boundaries:
            try:
                width_pixel = convert_width_to_pixels(geometry.width, geometry.width_unit, self.wcs)
                left, right = width_boundaries(samples, width_pixel)
                polygon = np.vstack((left, right[::-1]))
                self._path_artists.extend(
                    self.axes.fill(
                        polygon[:, 0], polygon[:, 1],
                        facecolor=geometry.display_color, edgecolor="none",
                        alpha=min(0.28, 0.20 * geometry.display_alpha), zorder=18,
                    )
                )
            except (ValueError, TypeError):
                pass

    def _on_motion(self, event: Any) -> None:
        if event.inaxes is not self.axes or event.xdata is None or event.ydata is None:
            return
        x, y = float(event.xdata), float(event.ydata)
        value: float | None = None
        if self.frame is not None:
            xi, yi = int(round(x)), int(round(y))
            if 0 <= yi < self.frame.shape[0] and 0 <= xi < self.frame.shape[1]:
                value = float(self.frame[yi, xi])
        world: tuple[float, float] | None = None
        world_unit: str | None = None
        if self.solar_map is not None:
            try:
                coordinate = self.solar_map.pixel_to_world(x * u.pix, y * u.pix)
                if hasattr(coordinate, "Tx") and hasattr(coordinate, "Ty"):
                    world = (
                        float(coordinate.Tx.to_value(u.arcsec)),
                        float(coordinate.Ty.to_value(u.arcsec)),
                    )
                    world_unit = "arcsec"
                else:
                    world = (
                        float(coordinate.spherical.lon.to_value(u.deg)),
                        float(coordinate.spherical.lat.to_value(u.deg)),
                    )
                    world_unit = "deg"
            except Exception:
                world = None
        elif self.wcs is not None:
            try:
                wx, wy = self.wcs.pixel_to_world_values(x, y)
                world = float(np.asarray(wx)), float(np.asarray(wy))
                units = getattr(self.wcs, "world_axis_units", None)
                world_unit = ",".join(units[:2]) if units else None
            except Exception:
                world = None
        self.cursor_changed.emit(
            {"x": x, "y": y, "value": value, "world": world, "world_unit": world_unit}
        )
        self.mouse_moved.emit(event)

    def _on_press(self, event: Any) -> None:
        if event.inaxes is self.axes:
            self.mouse_pressed.emit(event)

    def _on_release(self, event: Any) -> None:
        if event.inaxes is self.axes:
            self.mouse_released.emit(event)

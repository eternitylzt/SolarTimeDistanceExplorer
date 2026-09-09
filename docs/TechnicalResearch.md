# Technical research and library decisions

Research was completed before implementation against the official documentation
linked below (checked 2026-09-08). The project treats these APIs as upstream
contracts rather than copying blog implementations.

## Decisions

| Area | Library / official capability | STDE decision |
| --- | --- | --- |
| Solar FITS metadata and maps | [SunPy Map](https://docs.sunpy.org/en/stable/reference/map.html), Map factory, MapSequence | FITS folders have an optional lazy SunPy Map adapter. Generic FITS is never rejected merely because Map does not recognize its instrument. |
| Official solar coordinate-path extraction | [pixelate_coord_path](https://docs.sunpy.org/en/stable/generated/api/sunpy.map.pixelate_coord_path.html), [sample_at_coords](https://docs.sunpy.org/en/latest/api/sunpy.map.sample_at_coords.html) | paths/sunpy_backend.py exposes the official zero-width nearest-neighbour backend. It is not the default finite-width method because sample_at_coords is nearest-neighbour and errors for off-map coordinates. |
| Solar TD reference | [SunPy time-distance showcase](https://docs.sunpy.org/en/latest/generated/gallery/showcase/time_distance.html) | STDE follows the documented two approaches: reproject to a reference WCS or transform reference coordinates to every frame. First release implements the latter as World-coordinate fixed mode. It does not silently reproject. |
| Differential rotation | [propagate_with_solar_surface](https://docs.sunpy.org/en/stable/generated/api/sunpy.coordinates.propagate_with_solar_surface.html) | Reserved as an explicit experimental mode. The SunPy example uses it with a SphericalScreen; first release raises an explanatory message instead of applying an incomplete correction. |
| FITS / WCS | [Astropy FITS](https://docs.astropy.org/en/stable/io/fits/), [Astropy WCS](https://docs.astropy.org/en/stable/wcs/) | Astropy parses headers, memmaps cubes, and supplies high-level pixel/world transforms. Pixel origin conventions are handled through its API, not handmade FITS coordinate arithmetic. |
| Legacy SSW FITS metadata | [SunPy: Fixing incorrect metadata](https://docs.sunpy.org/en/latest/how_to/fix_map_metadata.html), [Astropy WCS constructor](https://docs.astropy.org/en/latest/api/astropy.wcs.WCS.html) | An adapter repairs known `map2fits` spelling/unit conventions before Map creation, then constructs WCS with `relax=True`, `fix=True`, and safe unit translation. This follows SunPy's documented recommendation to correct invalid metadata before constructing a Map. |
| Time | [Astropy Time](https://docs.astropy.org/en/stable/time/) and [FITS time conventions](https://docs.astropy.org/en/stable/io/fits/usage/table.html) | Internal temporal representation is Astropy Time; DATE-OBS variants, MJD, and linear TIME WCS are parsed. A frame index is only available after an explicit user choice. |
| Image normalization/WCS display | [Astropy visualization](https://docs.astropy.org/en/stable/visualization/), [WCSAxes](https://docs.astropy.org/en/stable/visualization/wcsaxes/) | Image normalization uses Astropy intervals/stretch objects. Valid celestial WCS frames use Matplotlib WCSAxes rather than painted coordinate labels. |
| SAV | [scipy.io.readsav](https://docs.scipy.org/doc/scipy/reference/generated/scipy.io.readsav.html) | SciPy is the only SAV parser; the GUI identifies standard SSW maps plus numeric image/cube fallbacks. |
| AIA Level-1 preparation | [aiapy preparing data](https://aiapy.readthedocs.io/en/latest/preparing_data.html), [register](https://aiapy.readthedocs.io/en/stable/api/aiapy.calibrate.register.html) | Full-disk AIA Level-1 maps use aiapy register, the current maintained implementation derived from aia_prep. Pixels and the registered WCS stay in the same dataset layer. |
| SSW maps | [SSW map structure documentation](https://hesperia.gsfc.nasa.gov/rhessidatacenter/complementary_data/maps/) | SAV structures with DATA/XC/YC/DX/DY are recognized. Their centre and scale become HPC FITS WCS; non-map arrays fall back explicitly to pixels. |
| Subpixel finite-width sampling | [scipy.ndimage.map_coordinates](https://docs.scipy.org/doc/scipy/reference/generated/scipy.ndimage.map_coordinates.html) | Used in constant/NaN mode for nearest, linear, and cubic interpolation. This is required for noninteger width, curved path normals, and safe out-of-FOV values. |
| Curves | [SciPy interpolation](https://docs.scipy.org/doc/scipy/reference/interpolate.html) | splprep/splev creates a dense B-spline; STDE reparameterizes by measured arc length before sampling. |
| Spline smoothing meaning | [SciPy smoothing splines](https://docs.scipy.org/doc/scipy/reference/generated/scipy.interpolate.make_splprep.html) | The GUI's `s` is the weighted squared-residual allowance: zero interpolates control points; increasing it permits a smoother approximation. It is not slit width or spatial sample step. |
| Scientific plotting | [Matplotlib pcolormesh](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html) | TD images use N+1 true temporal edges; imshow with an extent is not used for irregular cadence. |
| GUI concurrency | [PySide6 QThread](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThread.html) and [QThreadPool/QRunnable](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QThreadPool.html) | A QThread owns TD computation; it emits progress/data only and never touches a QWidget. |
| Movies | imageio-ffmpeg bundled executable | Equal-size PNG frames are passed directly to FFmpeg. MP4 uses H.264/yuv420p/even dimensions/faststart and is decode-checked before success; this avoids generic writer metadata discovery and improves Windows player compatibility. |
| Windows distribution | [PyInstaller](https://pyinstaller.org/en/stable/) | The supported build is onedir. PyInstaller's maintained PySide6 hooks collect Qt; the spec adds Matplotlib, Astropy, SunPy, certifi, and imageio-ffmpeg package data. |

## Scientific consequence of the SunPy backend choice

SunPy's documented pixelate_coord_path returns every pixel intersected by a
coordinate path and sample_at_coords obtains its values. The latter is
nearest-neighbour and intentionally raises for out-of-map samples. That is an
excellent reproducibility path for traditional one-pixel Map measurements, and
STDE keeps it as an adapter.

The application must additionally support a noninteger scientific slit width,
normal-direction average, curved spline geometry, linear/cubic sampling and
NaN outside a frame. These properties cannot be implemented by only wrapping
the SunPy pair. Therefore the default engine transforms a saved WCS path into
each Map's pixel WCS and calls SciPy map_coordinates in NaN constant mode.
This extends rather than replaces SunPy's coordinate semantics.

## Version compatibility

The dependency ranges in requirements.txt are deliberately not exact pins:
Python 3.11/3.12, NumPy 1.26–2.x, SciPy 1.11+, Astropy 6–8, SunPy 6–8, aiapy 0.12,
Matplotlib 3.8+, and PySide6 6.6+ are intended. The actual build writes the
installed versions into the About dialog and PyInstaller run logs.

## Interactive performance policy

Folder headers and timestamps are scanned once. Decoded/registered maps use a
bounded LRU rather than unbounded RAM, while every successful expensive AIA
registration is written to a session-temporary prepared FITS cache. Reopening a
frame outside the RAM LRU therefore performs disk decoding and Map construction,
but never repeats `aiapy.calibrate.register`. The GUI draws a decimated preview
with the original full-pixel extent and reuses WCSAxes; extraction and exported
scientific frames continue to request the full registered array.

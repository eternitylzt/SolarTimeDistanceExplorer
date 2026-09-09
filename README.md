# Solar Time–Distance Explorer

Solar Time–Distance Explorer (STDE) is a Windows desktop application for loading
solar-physics image time series, interactively placing a straight, polyline, or
smooth-curved slit, and producing scientifically reproducible time–distance (TD)
diagrams. It is a source-first project: FITS folder sequences are lazily read,
FITS cubes use memory mapping where possible, and the numerical engine is usable
without the GUI.

Author: **Zhentong Li** — eternitylzt@gmail.com —
[GitHub](https://github.com/eternitylzt/SolarTimeDistanceExplorer)

> Status: functional research preview (`0.8.0`). The core extraction algorithm,
> FITS/SAV readers, Qt GUI, export, project files, tests, and Windows packaging
> recipe are included. See [known limitations](#known-limitations) before using
> a result in a publication.

This is an early public research preview. Please report reproducible problems,
sample-data compatibility issues, and Windows packaging feedback through the
[SolarTimeDistanceExplorer issue tracker](https://github.com/eternitylzt/SolarTimeDistanceExplorer/issues).

## Quick start (Windows)

Recommended runtime: Python 3.11 or 3.12 (64-bit).

```powershell
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe main.py
```

Or use `build.ps1`, which creates `.venv`, installs dependencies, runs tests,
and creates an onedir Windows build in `dist/SolarTimeDistanceExplorer/`.

## Inputs

* **Single 2-D FITS image**: File → Open Single FITS Image provides a dedicated
  scientific preview. Explicit celestial/HPC metadata are rendered by SunPy
  Map/WCSAxes; incomplete metadata falls back visibly to pixel axes.
* **FITS folder** (`.fits`, `.fit`, `.fts`): each file is scanned independently;
  primary and image-extension headers are merged, SunPy/Astropy parse the real
  observation timestamps, and files are sorted by those timestamps. Irregular
  cadence is retained. Natural filename order is used only when no file has a
  usable observation time.
* **3-D FITS cube**: AUTO examines `CTYPE`, `CUNIT`, and dimensions; users can
  override Axis 0/1/2 before use. Data are accessed using FITS memmap.
* **SDO/AIA Level-1 FITS**: detected full-disk AIA Level-1 maps are registered
  with `aiapy.calibrate.register`, the maintained Python implementation derived
  from `aia_prep`. The prepared data and prepared WCS are used together. Each
  prepared frame is also written to a session-temporary FITS cache so revisiting
  a frame after RAM-LRU eviction does not repeat the expensive registration.
  Version 0.8 also keeps the configured number of prepared Map objects in RAM,
  drops the duplicate raw frame after registration, decimates only the live
  preview, and updates an existing WCSAxes in place instead of rebuilding the
  plot and colorbar on every slider step. Full-resolution data remain available
  to TD/region calculations and scientific exports.
* **Legacy SSW `map2fits` FITS**: common non-standard cards (`SOLAR-X/Y`,
  `arcsecs`, `XCEN/YCEN/DX/DY`, `DATE_OBS`, `CROTA`, and CD-only matrices) are
  normalized in the data adapter before Astropy WCS/SunPy Map construction.
  Original pixels are unchanged, and the normalized header remains inspectable.
* **IDL SAV**: standard SSW maps are recognized from `DATA/XC/YC/DX/DY` and
  translated to SunPy HPC WCS when angular units are defensible. Numeric 2-D or
  3-D variables remain viewable with an explicit pixel-coordinate warning.

STDE preserves `astropy.time.Time` internally. When timestamps are missing, it
asks whether to use frame index or a supplied start time and cadence.

## Main workflow

1. **File → Open Single FITS Image**, **Open FITS Folder**, **Open FITS Cube**, or **Open SAV**.
2. Inspect the dataset summary, time status, and cadence in the left panel.
3. Browse using the slider or the Previous / Play-Pause / Next controls directly
   above the image. The image controls use
   scientific English names for `Colormap`, `Normalization`, `Stretch`,
   `vmin/vmax`, and editable lower/upper percentiles. Switching between Manual,
   Percentile, Min–Max and ZScale immediately updates the existing image artist;
   it does not reread FITS or repeat AIA preparation. Fixed normalization is the
   default for intensity-consistent movies.
4. Optionally select the magnifier in the image toolbar and drag a rectangle to
   zoom. Choose a reference frame, then select the shape directly from the New
   Slit drop-down. A line is completed with its second left-click; a polyline or
   curve is completed by double-clicking in place or right-clicking.
   Drag a completed control point or label to edit. Slit and Region editors now
   exclusively own the mouse only while their left-side page is active; switching
   Region → Slit and drawing again is supported. Left-click blank image space to
   deselect all handles while retaining checked publication overlays. Full
   instructions are under Help → Slit / Region Drawing Help.
5. Set scientific slit width, integration statistic, interpolation, tracking,
   and coordinate mode. **Show scientific width shadow** displays that sampling
   width as a live semi-transparent band. Display line width remains independent.
6. Click **Generate TD**. A worker thread keeps the UI responsive. The TD tab
   uses true timestamp bin edges (`pcolormesh`) by default, including irregular
   cadence.
7. Export figures (PNG/PDF/EPS/SVG/TIFF), animation (GIF/MP4), TD numerical data
   (NPZ/FITS/CSV/TXT), or save a `.stdproj` project.

Movie export defaults to the currently visible image coordinate range, so an
interactive zoom becomes the exported field of view for the whole sequence.
The dialog can instead select the full image and independently include WCS/pixel
axes, observation timestamp, title, colorbar, visible Slits, and visible Regions.
Frames are rendered at one exact size and encoded by the bundled FFmpeg using
the same playback-safe pipeline as EPS Live Viewer.

The main toolbar's **Save Current View** action dispatches to the visible Map,
Time–Distance, or Region Analysis tab. Its arrow menu can select one explicitly.
TD and region tabs also have their own save buttons and Matplotlib navigation
toolbars. All text drawn inside scientific figures is English; Chinese is kept
for workflow guidance and less obvious settings.
The Layout action on Image, Time–Distance, and Region toolbars applies persistent
Left/Right/Top/Bottom/WSpace/HSpace values, even when the page originally used
automatic constrained layout.

Slits default to S1, S2, … and regions to R1, R2, …. Their manager checkboxes
control visibility; selected markers can be renamed and styled independently.
Line colour/width and label text colour/background/size are independent settings.
Each new marker receives a distinct palette colour; region trend and histogram
curves use that same region colour.
Settings → Memory cache frames changes the bounded 2–20 frame RAM cache and
applies immediately to an open FITS folder; the default is 12.
Settings controls whether checked Slit and Region overlays remain visible when
switching the left-side analysis tab. TD tick labels offer fixed HH:MM:SS,
HH:MM, full date-time, or a custom `strftime` pattern.
Slope lines are annotated with velocity next to the selected ridge and expose
line colour/width/style plus annotation size controls. TD title, both axis
labels, axis/tick sizes, grid, colorbar, aspect, colormap, stretch and range are
configurable, and the x-axis title can optionally include the first timestamp.

## Closed-region analysis

The Regions panel is independent of slit/path extraction and supports multiple
simultaneous regions:

* Circle: left-click the centre, move the mouse to preview, then left-click the radius.
* Rotated rectangle: click both endpoints of one edge, move to preview the height,
  then click a third time.
* Polygon: click vertices and finish by double-clicking in place or right-clicking.
* Manual circle and rectangle entry supports centre, radius/side lengths, angle,
  Preview, and confirmation.
* Only checked regions are included in Map overlays, time trends, and current-frame
  histograms. Plot overlays each selected region's NaN-aware mean or sum versus real observation time.
  Histogram overlays use the selected current frame and an exact configurable bin width.
  The title includes the actual observation timestamp when available, and the
  display can be switched between bars and step lines. Histogram Y values can be
  raw counts or relative frequency. Distributions are ordered by peak height so
  small regions are drawn last and remain visible with their correct colours.
  Time trends can likewise switch between lines and grouped bars.
* Aggregated curves and histogram bins export to FITS, CSV, or tab-delimited TXT.
  The suggested filename includes the contributing region labels, for example
  `R1_R2_trend.fits` or `R2_histogram.csv`.
* Region figures expose editable English title/axis labels, time format, line
  style/width, marker, linear/log scale, grid, title/axis/tick and legend sizes.
  Legend size follows title size by default and can be controlled independently.
  Plot curves retain
  exactly the corresponding R1/R2/... outline colour.
  Standard Python/SciPy has no conforming IDL SAVE writer, so `.sav` export reports
  that limitation instead of writing a mislabeled file.

## Keyboard shortcuts

| Shortcut | Action |
| --- | --- |
| Left / Right | Previous / next frame |
| PageUp / PageDown | Jump 10 frames |
| Space | Play / pause |
| Enter | Finish a polyline/curve |
| Escape | Cancel path drawing |
| Delete | Delete active path |

## Scientific choices

* The matrix convention is `TD[distance_index, time_index]`.
* The generic backend uses `scipy.ndimage.map_coordinates` with `mode='constant'`,
  `cval=NaN`, so off-detector samples remain NaN rather than being clipped.
* Curves are spline-evaluated densely and then resampled by **arc length**.
* Width samples lie along the local normal. Their NaN-aware mean, median, sum,
  maximum, or minimum becomes the central-path sample.
* For valid WCS and World-coordinate mode, sampled reference points are retained
  in world values and transformed into each frame WCS. This handles frame
  pointing/scale offsets without silently coaligning data.
* SunPy integration converts each displayed solar FITS frame to `sunpy.map.Map`
  (the Python equivalent of SSW `fits2map`) and plots it through Map/WCSAxes;
  valid HPC metadata therefore appears as Solar-X/Solar-Y. The optional
  `pixelate_coord_path()` / `sample_at_coords()` functions provide a nearest-pixel
  compatibility backend. The default numerical backend is SciPy because it
  supports sub-pixel curved slits and finite width.
* The TD distance selector defaults to arcsec for valid solar WCS and can switch
  to pixel, km, or Mm. Angular distance is integrated along transformed world
  samples rather than inferred from point count.

## Test data

Generate known-truth data:

```powershell
./.venv/Scripts/python.exe tests/data_generator.py --output tests/generated
```

It creates a 100-frame FITS sequence with a Gaussian feature travelling along a
curved path, plus uniform and irregular cadence cubes. The automated test suite
checks its known TD ridge speed.

## Build an EXE

```powershell
./build.ps1
```

The supported target is **onedir**. Copy the whole
`dist/SolarTimeDistanceExplorer/` directory; do not move only the `.exe`.
MP4 is the default and its dialog sets output resolution, frame rate, codec and
bitrate. Frames are written to a private staging directory, then the bundled
`imageio-ffmpeg` executable is invoked directly. MP4 uses H.264 with even frame
dimensions, `yuv420p`, and `faststart`; the app decodes one output frame before
reporting success. GIF also uses the bundled executable and neither format
depends on a system FFmpeg installation.

## Known limitations

* IDL SAV is read with SciPy. SSW `DATA/XC/YC/DX/DY` map structures and numeric
  image/cube fallbacks are supported; arbitrary nested proprietary structures
  may still need conversion in IDL.
* AIA registration requires a full-disk Level-1 image. Cutouts are retained as
  their original SunPy map with a clear warning because aiapy correctly refuses
  to run full-disk registration on them.
* Closed-region geometry can be pixel-fixed or WCS/world-fixed. The latter stores
  a sampled boundary and transforms it through each frame WCS; it does not perform
  image reprojection or differential rotation.
* Solar differential rotation tracking is deliberately experimental and not
  enabled automatically. Fixed pixel and fixed world-coordinate tracking are
  production modes.
* Physical Mm conversion is offered only when an angular scale is known; it uses
  the standard solar angular-radius conversion and is labelled as such.
* Full sequence coalignment/reprojection is not automatic. STDE warns rather
  than mutating source observations.

Further usage details are in [docs/UserGuide.md](docs/UserGuide.md), mathematics
in [docs/Algorithm.md](docs/Algorithm.md), and library decisions in
[docs/TechnicalResearch.md](docs/TechnicalResearch.md).

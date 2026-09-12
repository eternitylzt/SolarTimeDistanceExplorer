# User guide

## Example 1: AIA FITS folder

1. Start SolarTimeDistanceExplorer.exe or run python main.py.
2. Choose File → Open FITS Folder and choose the folder containing AIA FITS.
   Full-disk AIA Level-1 images are registered to Level-1.5 geometry with
   aiapy. AIA cutouts remain readable but are not falsely treated as full-disk.
   The bottom status bar shows the current FITS name and scan progress. Opening
   another source automatically releases the preceding dataset caches.
3. Inspect Dataset: number of frames, start/end, cadence range and whether it is
   nearly uniform or irregular. If a real observation time is absent, choose
   Frame index deliberately, or enter ISO start time and cadence.
4. Use the image timeline, arrow keys, PageUp/PageDown or the Play/Pause button
   located between Previous and Next above the image. In Image choose
   Colormap, Normalization and Stretch. Percentile exposes editable lower/upper
   percentages; Manual exposes vmin/vmax. A changed mode or value redraws at once
   without rereading the FITS frame. Leave Fixed normalization selected for an
   intensity-consistent animation.
   The Animation FPS setting is also the live preview rate and takes effect
   immediately while the preview is playing.
5. If needed, click the image-toolbar Zoom button and drag around the subfield;
   click Zoom again before drawing (New Slit also deactivates it automatically).
   Set Reference frame. Open the New Slit drop-down and select the type for this
   new slit directly:
   - line: **left-click** start, then **left-click** end;
   - polyline: left-click vertices; double-click in place or right-click to finish;
   - smooth: left-click loop controls; double-click in place or right-click to finish.
   Drag any marker after completion to correct it; Esc cancels. Switching to Regions
   and later choosing a new Slit safely reactivates the Slit editor. Left-click blank
   image space to deselect all handles while keeping checked overlays visible for export.
   Use Help → Slit / Region Drawing Help for the same instructions in a scrollable,
   selectable window. Help text can be copied; About also provides clickable email
   and project-homepage links.
6. In Slit Parameters set Slit width = 5, Unit = arcsec (the WCS default), Integration = Mean,
   Interpolation = Linear. Enable Show slit width to preview the
   actual numerical strip as a live semi-transparent band; the solid centreline
   thickness is only a display style.
7. With reliable image WCS, select Coordinates = world and Tracking =
   world_fixed to sample the same solar locations even if WCS pointing changes.
8. Click Generate Time–Distance. A progress window allows cancellation.
   TD distance axis defaults to arcsec for valid WCS. Select pixel if detector
   distance is preferred; km and Mm are also available when angular scale is valid.
9. In Time–Distance, leave True observational time on for irregular cadence.
   Use Measure Velocity, click two ridge points, and read Δt, Δs, velocity from
   the status bar. Clear slope removes all measurement markers. Time labels can
    be HH:MM:SS, HH:MM, full date/time, or a custom `strftime` format.
    The TD controls also set axis-title/tick font size and whether the x-axis
    title includes the first UTC timestamp. Slope colour, width and annotation
    size, annotation text colour and velocity decimal precision apply both to new
    measurements and existing visible markers. Auto colors labels successive
    measurements v₁, v₂, … with matching line/text colours and no persistent
    endpoint circles. Drag a velocity label to reposition it. Disable Auto
    colors and choose All or the desired v_n under Selected—or click its
    line/label—before setting line, text and Text Background colours. Changing
    Line first matches Text to the same colour; Text can then be changed alone.
    Background colour/transparency is stored separately for every v_n. Velocity
    defaults to km/s and can be changed independently of the plotted distance
    axis. If the x-axis title includes Start time,
    zooming or panning updates it to the visible interval's left edge.
10. Edit the English plot title/axis labels, colormap/stretch/range, grid,
    colorbar, aspect, line style and font sizes as needed. Export the panel using
    Export TD figure (PDF/EPS/SVG preserve vector axes) and
    Export TD data (NPZ, FITS, or CSV plus result.json).

## Example 2: 3-D FITS

Choose File → Open 3-D FITS Cube. A high-confidence TIME CTYPE axis is shown
automatically. If no unambiguous temporal FITS axis is present, the software
requires Axis 0, 1, or 2 confirmation; it will never silently choose a small
dimension. Use a Date-OBS and linear time WCS if present, otherwise configure
time manually.

## Example 3: IDL SAV

Choose File → Open IDL SAV. A standard SSW map variable containing
`DATA/XC/YC/DX/DY` is identified and displayed with its solar coordinate scale.
For a non-map numeric 2-D image the app warns, then previews it with pixel axes.
For a numeric three-dimensional cube, select its time axis and optionally a
time/times/utc/date_obs/t_obs variable.

## Single-image scientific preview

Choose File → Open Single FITS Image. This mode does not request an artificial
cadence. The metadata panel states either Solar/world WCS or Pixel. With valid
HPC metadata, the plot labels are Solar-X and Solar-Y and the status bar reports
cursor world coordinates in arcsec.

Older FITS created by SSW `map2fits` are accepted through a compatibility layer
for common `arcsecs`, `SOLAR-X/Y`, `XCEN/YCEN/DX/DY`, `DATE_OBS`, rotation and
CD-matrix conventions. Use View → Current FITS Metadata to verify the normalized
HPC cards. If the remaining metadata are scientifically insufficient, the app
keeps the image visible and clearly falls back to pixels.

## Slit coordinates, tracking, distance and smoothing

Coordinates describes how the selected centreline is stored: pixel x/y or WCS
world values. Tracking describes how that stored line is placed in every frame:
the same pixels or the same world coordinates transformed through each frame's
WCS. TD distance unit affects only the cumulative vertical coordinate and does
not alter either choice. Curve smoothing `s=0` passes through the control points;
a larger `s` permits increasing squared residual for a smoother approximation.
Percentile display limits suppress the lowest/highest tail only for colour
contrast and never modify the exported TD matrix.

## Closed regions: trend and histogram

1. Open the Regions left tab, click New Region, and select circle, rectangle, or
   polygon directly from its drop-down menu.
2. Circle: click centre, move to inspect the live radius preview, click again.
3. Rectangle: click two endpoints of one edge, move to preview its signed height,
   then click a third time. This permits rotated rectangles.
4. Polygon: click each vertex; double-click in place or right-click closes it.
5. Alternatively use Manual Circle / Rectangle, enter centre and dimensions in
   pixels, click Preview, then OK.
6. Repeat to create multiple regions. Choose pixel or world tracking before
   creating each region.
7. Check exactly the regions to analyze, choose mean or sum, then Plot Time Trend.
   Only checked regions are overlaid against real observation time. Trends can use
   lines or grouped bars.
8. Set Histogram bin width (default 1.0 in image-value units), choose Bar or Line,
   and click Histogram to overlay current-frame distributions. Its title contains
   the selected frame's actual observation time whenever FITS/SAV time is known.
   The Y axis can be Count or Relative Frequency. Large distributions are drawn
   first so smaller selected regions remain visible on top with their own colours.
9. Export Last Region Data writes FITS, CSV, or TXT. IDL `.sav` writing is not
   supplied by SciPy; the app explains this rather than creating an invalid file.
   Suggested names contain the selected region labels (`R1_R2_trend.fits`, etc.).
10. The Region Analysis page can edit its English title and axis labels, time
    tick format, line style/width, marker, linear/log scales, grid, title/axis/tick
    and legend sizes,
    then save PNG/PDF/EPS/SVG/TIFF. Every curve keeps its region outline colour.
11. To inspect changing distributions, set inclusive Start/End/Step frames and
    click the range-histogram button. Alternatively, zoom the TD plot and use
    **Use current TD time range**. The Region page then shows Previous/Play/Next,
    a slider, exact frame time, and MP4/GIF export. Numerical histograms are
    calculated once and retained in memory; playback never re-reads the FITS
    cube. Dragging the slider is debounced and filled histograms use one fast
    step-patch per Region. Zooming or panning any histogram frame saves one
    shared x/y viewport and applies it to every other frame.
12. Histogram movie export runs in the background. Its dialog parallels image
    movie export: current/full viewport, output resolution, start/end/step, FPS,
    MP4 codec/bitrate, axes, actual time, title, legend, and grid are selectable.

## Saving work

The top toolbar's Save Current View button saves the plot visible on the right.
Use its arrow to choose Map, Time–Distance, or Region Analysis explicitly. These
exports call Matplotlib directly and are not screenshots. Figure labels and
default titles remain English for publication.
The export options can independently omit the colorbar, axes, or title and can
use a transparent figure background; the visible interactive canvas is not
modified by the export.
The Layout button on every plot toolbar controls and remembers figure margins
(Left/Right/Top/Bottom) and subplot spacing (WSpace/HSpace) for that page.

Animation export defaults to the image canvas's current coordinate limits. Zoom
or pan first, then export to make the movie/GIF follow that same field of view
for every frame. The export dialog can choose full image instead and toggle
coordinate axes, actual observation time, title, colorbar, Slits and Regions.

File → Save Project stores source locations, explicitly configured times,
reference frame, paths, world samples, widths, integration/interpolation and
display choices in .stdproj; image data are not duplicated. Opening it reloads
the source. If a source moved, point the dialog at its new location.

Settings → Clear Current Data Cache releases decoded frames and temporary
AIA-prepared FITS files while retaining the open dataset and currently displayed
frame. Subsequent frame access is intentionally read/prepared again.

Settings → Language switches the complete application interface between Chinese
and English. The preference is saved with the application settings. Accept the
restart prompt to relaunch automatically; declining applies it on the next start.

View → Drawing History opens independent historical views of maps, completed
markers, TD results, region trends, histograms, and histogram sequences. Deleted
or scientifically changed markers are explicitly marked as view-only. Matching
current markers can be selected for further analysis using an explicit button;
opening history itself does not change your current frame, results, or drawing.
Close the window or choose Return to Latest State to continue. Historical
histogram sequences have their own playback controls. The default history limit
is 20 and can be changed at the bottom of the menu.

If no control point has been placed, choosing another shape from New Slit or
New Region reuses the pending marker name instead of consuming a new number.

Help → Check for Updates... checks GitHub only when clicked. A newer version
offers a button opening that exact Release page; otherwise the dialog reports
that the app is up to date or shows a network error. No automatic download or
installation occurs. About also links directly to all Releases.

## Troubleshooting

* No FITS images found: verify extensions .fits, .fit, or .fts and that each
  data HDU is two-dimensional for folder input.
* World path unavailable: use Pixel mode, or inspect header WCS keywords under
  View → Current FITS Metadata.
* MP4 export fails: the release bundles `imageio-ffmpeg`; copy the whole onedir
  folder rather than only the EXE. MP4 is encoded as H.264/yuv420p with even
  dimensions and is decoded once before the app reports success.
* Why is the ZIP much larger than the EXE? The program uses reliable PyInstaller
  onedir packaging. `_internal` contains Python, Qt, NumPy/SciPy, SunPy/Astropy,
  and FFmpeg and is required. Version 1.0 removes unused package tests/data and Qt
  Addons, but the remaining scientific runtime cannot be deleted.
* TD has NaN at an edge: the slit lies outside that frame. NaN is intended and
  is scientifically safer than clipping.
* Sequence shifts: choose world-fixed tracking when WCS is valid. Do not assume
  STDE coaligned images; automatic reprojection is deliberately absent in this
  release.

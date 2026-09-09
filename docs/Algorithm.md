# Time–distance algorithm

## 1. Time coordinate

All trustworthy observations are represented by Astropy Time. Folder FITS files
use DATE-OBS, DATE_OBS, DATEOBS, T_OBS, DATE-BEG, DATE-AVG, then MJD variants.
Files are chronologically sorted only if every usable file has a parsed time;
otherwise a natural filename order is used and the time dialog is shown.

For a FITS cube, a selected temporal FITS WCS axis uses

t_i = CRVAL + ((i+1)-CRPIX) CDELT.

A TIME-like axis is made absolute only when DATE-OBS or MJDREF supplies an
epoch. A SAV numeric time array has no universal epoch, so it is not guessed.

For true-time graphics, centers t_i become bin edges at the midpoint between
observations, with linearly extrapolated first and last edges. Matplotlib
pcolormesh therefore makes a 35-s observation gap visibly wider than a 10-s
gap.

## 2. Centreline geometry

A line uses its two controls. A polyline joins its controls. A smooth path uses
SciPy B-spline evaluation only to produce a dense curve. In every case the code
measures cumulative image-plane arc length,

s_0 = 0; s_i = s_(i-1) + magnitude(r_i-r_(i-1)),

then linearly resamples x(s), y(s) at the requested pixel spatial step. Thus
the spline parameter is never reported as a distance axis.

## 3. Tangent, normal, and scientific slit width

At a resampled position the unit tangent is estimated by a centered numerical
gradient; the image-plane normal is N = (-Ty, Tx). For scientific width W,
normal offsets n_j cover [-W/2, W/2]. This is entirely distinct from the
Matplotlib display linewidth. The data value is the mean of

I(r(s) + n_j N(s), t)

over the offsets. Mean is default; median, sum, maximum, and minimum are also
available. Width one pixel is a single central subpixel sample; larger
noninteger widths use a symmetric interpolated strip.

## 4. Interpolation and invalid data

Image array coordinates follow NumPy order row=y, column=x. SciPy
map_coordinates evaluates nearest (order 0), linear (1), or cubic (3) samples.
It uses constant mode with NaN outside the detector; STDE never clips an
invalid coordinate to the detector edge. NaN source samples remain NaN-aware
through the width reduction. A fully invalid cross-strip produces NaN.

The product convention is TD[distance_index, time_index], so columns are times
and rows are cumulative distance samples.

## 5. WCS world-coordinate paths

When World mode is selected on a valid reference WCS, every already
arc-length-resampled reference sample is converted through pixel_to_world_values.
The first two world values are retained in the project. For each frame,
world_to_pixel_values creates that frame's sampling coordinates. This tracks
pointing / CRPIX / CDELT changes without modifying source images. Pixel mode
instead keeps the reference pixel coordinates fixed.

Arcsec distance is computed by transforming every resampled centerline point
through the WCS and summing projected angular separations. Longitude is
unwrapped before differencing at the 0/360-degree boundary. Pixel distance is
the cumulative image-plane arc length. km and Mm conversion is enabled only for
an angular WCS and uses nominal solar radius 695700 km and mean solar angular
radius 959.63 arcsec; the software never fabricates a scale for pixel-only data.

## 6. Exposure and preprocessing

Raw arrays are preserved. Exposure normalization is an opt-in calculation
parameter and fails cleanly if any selected frame lacks exposure metadata.
The FrameProcessor interface permits future running/base differences, smoothing,
and coalignment stages without embedding them in the GUI or mutating source
data.

## 7. Closed-region statistics

Circles are sampled as dense closed boundaries, rotated rectangles as four
vertices, and polygons as their user-selected vertices. Pixel-centre inclusion
uses a closed polygon test within the boundary's clipped bounding box. For
world-fixed regions the reference boundary is transformed through every frame's
WCS before rasterizing its mask. Non-finite pixels are excluded. The plotted
quantity is either the finite-pixel arithmetic mean or sum. Histograms use
explicit edges separated by the requested bin width; they never reinterpret the
width as a number of bins.

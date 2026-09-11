# Solar Time–Distance Explorer 1.0.0

The first stable research release.

- Fixed Region histogram sequences retaining grid lines after **Grid** was disabled, including cached-frame redraws.
- Replaced long message boxes with scrollable, selectable help pages. About now provides a copyable email address and clickable project homepage.
- Reduced distribution size with focused Astropy/SunPy hooks, test/data exclusions, and Qt Essentials instead of unused Qt Addons.
- Separated runtime and development dependencies and strengthened frozen scientific-runtime validation for FITS, WCS, SunPy Map, SciPy sampling, AIA registration imports, PDF/EPS, MP4, and GIF.
- Release pages now contain only the four native application archives; GitHub's asset digest remains available without separate SHA-256 text files.

Windows x64 is the primary tested platform. Linux and macOS builds are native, unsigned packages produced by GitHub-hosted runners.

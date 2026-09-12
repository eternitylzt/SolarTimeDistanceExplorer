# Local 1.2.3 validation

- Targeted tests exercise Auto colors order, actual modal frame-text editing in
  TD and Region plots, default restoration, cancel preservation, and resetting
  custom text when selecting a frame again. Style redraw retains custom text.
- No new dependencies or GitHub publication. Previous local builds are preserved.
- Full automated suite: 80 passed, 54 expected FITS date-fixup warnings.
- PyInstaller build and bundled scientific/session/PDF/EPS/MP4/GIF smoke passed.
  Actual EXE main-window startup and close passed with exit code 0.
- Output: `dist-1.2.3/SolarTimeDistanceExplorer/SolarTimeDistanceExplorer.exe` and
  `release/SolarTimeDistanceExplorer-1.2.3-Windows-x64.zip`.

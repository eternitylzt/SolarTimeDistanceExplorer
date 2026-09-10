# Solar Time–Distance Explorer 0.8.3

- Fixed the Slit rename/delete state split caused by NumPy-backed geometry equality.
- Slit and Region list operations now resolve rows exclusively through stable UUIDs.
- Slit width defaults to arcsec whenever valid celestial WCS is available.
- Renamed the TD tool to Measure Velocity and changed its default output to km/s.
- Added All plus per-`v_n` line, text, and Text Background styling.
- Changing a velocity line colour initially synchronizes its text colour; text can then be customized independently.
- Replaced the README with concise Chinese/English sections and quick language links.
- Added regression tests for renamed replacement Slits and per-marker velocity backgrounds.

Extract the complete Windows ZIP and run `SolarTimeDistanceExplorer.exe`; keep the EXE and `_internal` directory together.

# Solar Time–Distance Explorer 0.10.0

- Region histogram sequences retain their numerical frame results in memory and now use fast step-patch rendering plus slider-event debouncing.
- Zooming or panning any histogram frame establishes one viewport shared by all cached frames.
- Histogram MP4/GIF export now runs in the background and includes current/full viewport, resolution, frame range/step, FPS, codec, bitrate, axes, timestamp, title, legend, and grid controls.
- Added a complete Chinese/English application-language switch under Settings, with saved preference and optional automatic restart.
- Added regressions for cached result identity, cross-frame zoom preservation, large-bin artist count, configurable playable MP4 export, and full English static UI coverage.

Windows remains the primary tested platform. Linux and macOS packages are native, unsigned research-preview builds produced by GitHub-hosted runners.

# Solar Time–Distance Explorer

[中文](#中文说明) · [English](#english)

Cross-platform desktop software for solar-image browsing, interactive Slit/Region
analysis, true-time time–distance diagrams, animation, and publication-quality
export.

**Author:** Zhentong Li · eternitylzt@gmail.com ·
[GitHub](https://github.com/eternitylzt/SolarTimeDistanceExplorer)

> Current version: **1.1.0** — independent plot history and manual update checks.

## 中文说明

### 下载与运行

在 [GitHub Releases](https://github.com/eternitylzt/SolarTimeDistanceExplorer/releases)
Windows 用户下载 `SolarTimeDistanceExplorer-1.1.0-Windows-x64.zip`。完整解压后运行
`SolarTimeDistanceExplorer.exe`，无需另装 Python。请保留 EXE 与 `_internal`
目录的相对位置。EXE 约数十 MB，但它不是独立的 onefile 程序；`_internal` 中的
Python、Qt、NumPy/SciPy、SunPy/Astropy 与 FFmpeg 是离线运行 FITS/WCS、GUI 和视频
导出所必需的运行环境，不能只复制 EXE。

### 主要功能

- 打开单幅 FITS、FITS 文件夹序列、三维 FITS 和 IDL SAV。
- 逐文件解析真实观测时间，保留不规则 cadence；TD 使用真实时间 bin。
- SunPy Map/WCSAxes 显示 Solar-X/Solar-Y；兼容常见 SSW `map2fits` 头字段。
- AIA Level-1 使用 `aiapy.calibrate.register`，并通过内存与会话临时缓存避免重复 prep。
- 延迟读取 FITS、LRU 帧缓存、FITS cube memmap 和后台 TD 计算。
- 鼠标绘制、编辑和管理 Line、Polyline、Smooth Curve Slit。
- 默认使用 World/WCS 坐标、world-fixed tracking、arcsec Slit width、arcsec TD 距离及曝光时间归一化（可关闭）。
- 科学 Slit width 在路径法向参与 Mean/Median/Sum/Maximum/Minimum 统计；显示线宽仅影响外观。
- 多个 Circle、Rotated Rectangle、Polygon Region 的时间趋势、当前帧直方图和帧范围直方图动画。
- 帧范围直方图结果一次计算后保存在内存中；阶梯填充渲染和滑块防抖使播放/拖动更流畅，任一帧的缩放/平移范围会用于整个序列。
- 直方图动画在后台导出，可设置当前/完整范围、分辨率、起止帧、步长、FPS、编码器、码率、坐标轴、时间、标题、图例和网格。
- **设置 → 语言 / Language** 可在中文与完整英文界面之间切换；选择后可自动重启并应用。
- Help 内容使用可滚动、可选择复制的阅读窗口；About 中可复制邮箱并点击项目主页。
- 速度测量默认输出 km/s；支持 `v₁、v₂…`、All/逐项样式、可拖动文字及独立 Text Background。
- GIF/MP4、PNG/PDF/EPS/SVG/TIFF、TD/Region FITS/NPZ/CSV/TXT 和 `.stdproj` 项目文件。
- 未落点前更换 Slit/Region 形状，保留原编号，不占用新名称。
- 绘图历史在独立窗口保留 TD、趋势和直方图序列；删除或修改标记后仍可查看，不干扰当前绘制。关闭历史或点击“回到最新状态”即可继续操作。
- Help → **Check for Updates...** 仅手动检查版本，提供 Release 下载页面；不后台检查、不自动下载或安装。About 也提供 Releases 链接。

### 快速使用

1. 通过 **文件** 菜单打开数据，检查帧数、起止时间和 cadence。
2. 使用图像上方 Previous / Play-Pause / Next、滑块和 FPS 浏览序列。
3. 在 **切片** 页从 **New Slit** 下拉菜单选择形状：
   - Line：依次点击起点、终点；
   - Polyline / Smooth Curve：连续点击控制点，双击原地或右键完成；
   - 完成后拖动控制点或标签；点击图像空白处取消选中手柄。
4. 设置 Slit width、Unit、积分方式、坐标和逐帧跟踪，生成 TD。
5. 在 TD 图上点击 **测量速度**，依次点击传播结构上的两点。关闭 Auto colors 后，
   Selected 可选 All 或单个 `v_n`；修改 Line 会先让文字同步同色，之后可单独修改 Text。
6. 在 **区域** 页选择 Circle、Rectangle 或 Polygon，只分析列表中勾选的区域。
   可设置 Start/End/Step，或缩放 TD 后点击 **使用 TD 当前时间范围**；生成的
   直方图序列可逐帧播放并导出 MP4/GIF；在一帧中框选放大或平移后，整个序列和“当前范围”导出都会使用同一视口。
7. 使用各图页保存按钮或顶部 **保存当前视图**；图像输出由 Matplotlib 生成，不是界面截图。

完整操作见 [docs/UserGuide.md](docs/UserGuide.md)，算法见
[docs/Algorithm.md](docs/Algorithm.md)。

### 从源码运行与构建

推荐 Python 3.11/3.12 64-bit：

```powershell
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe main.py
```

测试并生成 Windows onedir 与 ZIP：

```powershell
./build.ps1
```

输出位于 `dist/SolarTimeDistanceExplorer/` 和 `release/`。

### 多平台基础

- Windows x64：主要验证平台，Release 提供完整 onedir ZIP。
- Linux x64：GitHub Actions 在 Ubuntu 原生构建 tar.gz；目标系统需有常规 OpenGL/EGL/XCB 桌面运行库。
- macOS Apple Silicon / Intel：分别在对应 runner 原生构建 `.app` ZIP。

Linux/macOS 包由 `.github/workflows/multiplatform-release.yml` 在对应系统构建，
不是 Windows 交叉编译。当前 macOS 包未做 Apple 开发者签名/公证，首次运行可能需要
在“隐私与安全性”中确认；它们属于研究预览版。Unix 开发者可运行 `bash build_unix.sh`。
Release 仅发布各平台程序压缩包，不再附带零散的 `.sha256.txt`；GitHub 会在每个
Release asset 上提供 digest 信息。

### 快捷键

| 按键 | 功能 |
| --- | --- |
| Left / Right | 上一帧 / 下一帧 |
| PageUp / PageDown | 跳转 10 帧 |
| Space | 播放 / 暂停 |
| Enter | 完成 Polyline / Curve |
| Escape | 取消当前绘制 |
| Delete | 删除活动标记 |

### 已知限制

- 不自动执行全序列重投影、图像配准或太阳差分自转校正。
- AIA full-disk Level-1 可注册；cutout 保持原 Map，不伪装为 Level-1.5。
- 任意 IDL 私有嵌套结构不保证识别；标准 SSW Map 和数值数组可用。
- km/Mm 与 pixel/arcsec 的互换需要可靠 WCS 像素尺度。
- 发布前请用已知真值数据核验路径、WCS、单位及速度结果。

问题反馈：[GitHub Issues](https://github.com/eternitylzt/SolarTimeDistanceExplorer/issues)

---

## English

### Download

Download `SolarTimeDistanceExplorer-1.1.0-Windows-x64.zip` from
[GitHub Releases](https://github.com/eternitylzt/SolarTimeDistanceExplorer/releases),
extract the complete folder, and run `SolarTimeDistanceExplorer.exe`. Python is
not required. Keep the EXE beside its `_internal` directory.
The EXE is only the launcher/application archive in PyInstaller onedir mode.
The `_internal` directory contains the bundled Python, Qt, scientific stack,
and FFmpeg needed for offline FITS/WCS analysis and movie export, so it is required.

### Highlights

- Single FITS preview, FITS folders, 3-D FITS cubes, and IDL SAV input.
- Per-file `astropy.time.Time` detection and true irregular-cadence TD bins.
- SunPy Map/WCSAxes solar coordinates, common SSW `map2fits` compatibility, and
  cached AIA Level-1 registration through `aiapy`.
- Lazy FITS access, LRU frame cache, cube memory mapping, and cancellable TD workers.
- Editable Line, Polyline, and arc-length-resampled Smooth Curve Slits.
- World-coordinate storage/tracking when WCS is valid. Defaults are arcsec Slit
  width, arcsec TD distance, and exposure normalization.
- Real finite-width normal sampling with configurable statistic and interpolation.
- Multi-Region trends, current-frame histograms, and playable frame-range histogram sequences.
- Histogram arrays are computed once and cached in memory. Step-patch rendering,
  slider debouncing, and a sequence-wide zoom/pan viewport keep review responsive.
- Histogram movies export in a background worker with current/full viewport,
  resolution, frame range/step, FPS, codec, bitrate, axes, time, title, legend,
  and grid controls.
- **Settings → Language** switches between a fully Chinese or fully English UI;
  the application can restart automatically to apply the choice cleanly.
- Help pages are scrollable and selectable; About exposes a copyable email link
  and clickable project homepage.
- Velocity measurements default to km/s. Markers `v₁, v₂…` support automatic
  colours or All/per-marker line, text, text size, and text-background styling.
- Publication figures, GIF/MP4, numerical TD/Region exports, and JSON project files.
- Changing an unstarted Slit/Region shape preserves its name and identifier.
- Independent plot history retains TD/Region results after marker deletion without
  disturbing current drawing. Close history or choose **Return to Latest State** to resume.
- Help → **Check for Updates...** manually checks the latest release and opens its
  download page. No background checks, automatic downloads, or installation.

### Workflow

1. Open data and verify its timestamps/cadence.
2. Browse or animate frames; zoom before drawing or movie export if required.
3. Choose the shape from **New Slit**. A Line finishes on its second click;
   Polyline/Smooth Curve finishes on a double-click or right-click.
4. Configure Slit width, coordinates, tracking, integration, and interpolation;
   then generate the TD diagram.
5. Click **Measure Velocity** and choose two points. Disable Auto colors to edit
   All markers or one selected `v_n`. Changing Line colour initially matches its
   Text colour; Text and Text Background remain independently editable.
6. Use Regions for trends, current-frame distributions, or a Start/End/Step
   histogram sequence. The visible TD range can fill this range; sequences have
   slider/playback controls and MP4/GIF export. Zoom/pan one histogram frame to
   apply that viewport across the sequence and its current-view movie export.

See [docs/UserGuide.md](docs/UserGuide.md) for detailed operation and
[docs/Algorithm.md](docs/Algorithm.md) for the scientific definitions.

### Source and native builds

```powershell
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe main.py
./build.ps1
```

`build.ps1` runs the test suite and creates the complete optimized onedir package
and release ZIP. Runtime dependencies are in `requirements.txt`; test/build tools
are separated into `requirements-dev.txt`.

On Linux or macOS, use `bash build_unix.sh`. Tagged releases are built natively
on Windows x64, Linux x64, macOS Apple Silicon and macOS Intel by GitHub Actions.
Windows remains the primary verified platform; unsigned Unix packages are research previews.
Release pages contain only the native archives. GitHub displays an asset digest,
so separate checksum text files are no longer published.

### Scientific notes

- Internal matrix convention: `TD[distance_index, time_index]`.
- Curves are resampled by physical arc length, not spline parameter.
- Off-detector samples remain NaN; they are never silently clipped.
- World-fixed mode transforms retained world samples through each frame WCS but
  does not silently reproject the images.
- Differential-rotation tracking remains experimental.

Please report reproducible issues through
[GitHub Issues](https://github.com/eternitylzt/SolarTimeDistanceExplorer/issues).

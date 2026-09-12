# Research tools — 1.2.3

[中文](#中文) · [English](#english)

## 中文

原来的打开、绘制、生成、导出流程保持不变。

### 1.2.3

Auto colors 位于 Selected 前。帧标记样式中的“标记文字”可自由编辑、换行或删去
Frame 编号；“恢复默认文字”恢复当前帧的自动标注。确认后生效，取消不会更改文字。
重新选帧时会重置为该帧的默认文字，不把旧时间误用在新帧上。

Auto colors now precedes Selected. Frame style offers a multiline label editor and
Restore default text. Confirm applies edits; Cancel discards them. Picking a frame
again resets its label to the correct default timestamp.

### 1.2.2 操作调整 / Changes

- TD/区域图选帧后，文字默认位于虚线旁边。拖动文字改变位置；双击文字或点击“帧标记样式”设置线条颜色/宽度/线型、文字颜色/字体/字号/背景。“清除帧标记”仅删除帧标记，不删除测速结果。
- 取消独立加速度模式。多点拟合自动做线性速度拟合与独立二次加速度估计。“显示加速度”只在多点模式下出现，仅控制图中文字，不改变速度线、阴影或计算结果。
- 加速度的数值、误差与二次拟合残差始终可在拟合详情中复制。3个不同时间点可以确定加速度，但不能估计统计误差；至少4点才有残差自由度。仅对整体持续加速/减速结构有意义。
- Frame labels start beside the time line and can be dragged. Double-click the label or use Frame style to set line/text appearance. Clear frame removes only that frame selection.
- OLS automatically estimates a separate quadratic acceleration; Show acceleration only controls the annotation. The velocity line and its mean uncertainty band remain linear. Fit details always expose acceleration and quadratic residuals. Three distinct points determine acceleration but not its uncertainty; 4+ permit residual-based error estimation.
- Previous-session acceleration modes are mapped to OLS controls; saved historical fits remain intact.

### 1.2.1 操作调整

- 质量报告后台检查已加载头信息，显示进度并可取消；相同空间 WCS 只验证一次，不读取图像或重复 AIA prep。
- TD 的“绘图区形状”为自动、正方形、宽屏；仅改变物理画框长宽，不再把天与角秒强行等比例，不影响数据和测速。
- 多点拟合至少3点，保留点击位置；半透明带为拟合均值的1σ统计不确定度，非预测散布或总物理误差。
- 加速度采用 `s=b+v(t-t0)+a(t-t0)^2/2`。1.2.1 的独立模式已在1.2.2合并入多点拟合，详见上方新说明。仅适合整体持续加速/减速轨迹；请检查残差，不能替代局部动力学分析。方向反转时提示；单位转换沿用同一投影尺度。
- TD/区域工具栏：点击“在图上选帧”，在时间位置点击，再点“查看对应图像”。直方图选择当前显示的帧；序列可先拖动滑块。
- 区域面板按时间变化、直方图设置、绘制按钮排列；“使用 TD 当前时间范围”将可见范围应用到帧范围输入框，位于播放帧率之前。
- 查看菜单可复制当前数据路径并打开所在文件夹。分析说明并入原有绘制与科学参数帮助，不再单列升级说明。

### 1.2.1 changes (English)

Quality reports now scan cached headers in a cancellable background worker and
reuse identical spatial-WCS validation. Plot shape controls physical box dimensions,
not equal date/distance units. OLS (3+ points) retains picks and a 1σ fitted-mean band.
Global acceleration (4+ points) fits a constant-acceleration quadratic; use only for
overall speeding-up/slowing-down tracks, inspect residuals, and heed direction-reversal
warnings. The label reports interval-mean velocity and acceleration. Statistical errors
exclude tracing, WCS and projection systematics. Pick frame then Show frame image links
TD/trends to images; histogram picks select the displayed frame. View > Current data
location shows a copyable path and folder link. Region controls follow analysis order.

Plot-box implementation follows [Matplotlib box aspect](https://matplotlib.org/stable/gallery/subplots_axes_and_figures/axes_box_aspect.html);
fit bands use [Matplotlib fill_between](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.fill_between.html).

| 功能 | 入口 | 默认行为 |
| --- | --- | --- |
| 数据质量 | 数据集 → 数据质量报告 | 不修改数据；检查时间、曝光、WCS、观测者距离 |
| 撤销/重做 | 编辑菜单，Ctrl+Z / Ctrl+Y / Ctrl+Shift+Z | 仅编辑 Slit/Region，不回滚科学结果；最多100次 |
| 分析会话 | 文件 → 保存/打开分析会话 | `.stdsession` 保存结果、标注、视图、绘图历史，原始数据仍引用 |
| 缓存预算 | 设置 → 缓存内存预算 / 性能统计 | 缓存数组总预算512 MiB，同时遵守原有帧数上限 |
| 多点速度 | TD → Two points / OLS fit / Segmented | 默认保留两点；多点右键、双击或 Enter 完成，Esc取消 |
| 观测缺口 | TD → Show gaps | 默认关闭；开启后可调阈值，默认5倍正时间间隔中位数 |
| 覆盖检查 | 区域图 → Trend quantity | Signal、Valid pixels 或 Valid area，原始数值不改变 |

### 数据与科学含义

- 质量报告复用头信息，不预加载完整图像。时间字段的存在不等于所有字段均正确；报告还显示解析后的重复/逆序时间与异常缺口。
- 对三维 FITS/SAV，单帧头时间可能缺失，但时间数组仍有效，应结合“时间轴来源”判断。
- WCS 可解析仅代表角度坐标可用，不保证指向精度或已经配准。
- 当前 km/Mm 换算沿用名义太阳尺度：695700 km / 959.63 arcsec。不是依据逐帧观测者距离去投影的真实表面距离。缺失观测者信息时 SunPy 可能采用地球视角，质量报告会提醒。
- OLS 拟合 `s = v(t-t0)+b`，显示残差估计的 **1σ斜率标准误**；假定时间准确、距离误差独立且同方差，不含人工描迹、WCS、投影误差。两点和分段两点模式不能估计残差误差。
- “拟合详情”可复制选点与残差；图像和 TD 数据的参数文件同样保存这些数据。不规则 cadence 在 Uniform frame spacing 视图中测速时仍使用真实时间。
- Show gaps 只插入空白绘图列，不删除或插补 TD 数值。缺口两侧各保留半个中位 cadence；这不是曝光时间估计。
- 区域均值/总和只用有限值像素。导出包含有效像素数、视场内 mask 像素数和近似角面积（WCS 像素尺度平方）。**不自动补偿视场外缺失部分**；有效面积变化时应谨慎解释 Sum。
- 直方图序列所有帧及区域使用同一组 bin 边界；Count 与 Relative Frequency 均可导出。频率是 bin 内像素数除以该区域该帧有效像素总数，不是概率密度。

### 会话、历史与可重复性

`.stdproj` 继续保存轻量参数；`.stdsession` 为 JSON/压缩 NPY 归档，不使用 pickle。
它保留当前 TD、区域结果、直方图序列、速度标注、各图缩放范围和已有绘图历史。
原始 FITS/SAV 不写进归档；重新打开需要原始数据，移动后可重新定位。
恢复前检查帧数、形状及源文件大小/修改时间；这不是内容哈希校验，不能识别刻意保留大小/时间戳的内容替换。
会话当前限制为2 GiB解压数据；直方图序列数值缓存限制512 MiB，过大时增加 bin width 或 frame step。

新导出的科研图片旁有 `图片文件名.扩展名.json`，记录计算参数、图样式、视图范围和版本。
区域数值导出也有同名 JSON；TD 数值继续使用 `.result.json`，FITS 内保留 PARAMETERS HDU。
TD FITS 使用64位浮点保存，避免额外降精度。
图像只会包含英文科研标签；复杂操作解释提供中英文界面。

### 性能与边界

缓存计数仅覆盖原始帧/Map 数组，共享数组可能保守重复计数；不包括 Qt/Matplotlib、
当前显示、计算结果、原始 SAV 立方或 OS 文件缓存，因此不等于整个进程内存。
最近使用的帧优先保留，AIA 磁盘 prep 缓存仍有效；重新清除缓存后读取会再次变慢。
性能统计分别记录读取与图像绘制耗时，最近100次，包含正常 GUI 排队等待。
直方图播放复用图形对象，但高 DPI 绘制仍可能占据主要时间；不承诺所有数据均达到设定 FPS。

## English

This is a local, unpublished preview. No new third-party dependencies are required.

- **Dataset → Data Quality Report** inspects cached headers, parsed time intervals,
  exposure and angular WCS availability. Header WCS is not a pointing calibration.
- **Edit → Undo/Redo** manages up to 100 Slit/Region edits independently of plot history.
  Text fields keep their own undo. Continuous drags/parameter changes are coalesced.
- **File → Save/Open Analysis Session** stores results, measurements, viewports and
  history in `.stdsession` (JSON/NPY, no pickle or raw image cubes). Original sources
  are required to resume; relocated files can be selected. Frame shape/count and
  file size/mtime must agree. This is not a cryptographic identity check.
- **Settings → Cache Memory Budget / Performance Statistics** provides a 512 MiB
  default cached-payload budget in addition to the existing frame-count limit.
  Active images, results, GUI objects and raw SAV cubes are outside that budget.
- **TD → OLS fit / Segmented** adds multipoint fitting; right-click/double-click/Enter
  finishes and Escape cancels. Fit details and export sidecars retain picked points
  and residuals. OLS standard errors assume exact times and independent equal-variance
  distance errors; tracing/WCS/projection systematics are excluded. Two points cannot
  estimate residual-based error. Irregular observational timestamps are also used
  for velocities when viewing uniformly spaced frames.
- **TD → Show gaps** optionally blanks intervals exceeding a configurable multiple
  of median cadence (default5), without modifying the TD matrix or inferring exposure.
- **Region → Trend quantity** switches between signal, finite-pixel count and
  approximate angular area. Exports retain signal, valid counts, in-FOV mask counts
  and angular area. Missing-area compensation is deliberately not performed.
- Histogram sequences share edges across all frames/regions. Exports include count
  and relative frequency (not probability density). Cached artists/axes are reused.
- Figure/Region sidecars record source identities, precise times, parameters,
  software version and display options. TD numerical exports retain `.result.json`
  and FITS PARAMETERS; TD FITS arrays now use float64.

km/Mm conversions retain the nominal projected solar scale (695700 km / 959.63 arcsec),
not a frame-specific observer-distance or deprojection model. Read the quality
report before interpreting physical velocities. Session uncompressed payloads are
limited to2 GiB; histogram caches to512 MiB. These are not whole-process limits.

### Implementation references

OLS uses [NumPy least squares](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html).
Editing uses [Qt undo commands](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QUndoStack.html).
Sessions preserve [Astropy Time's two-part Julian date](https://docs.astropy.org/en/stable/time/index.html).
Gap rendering uses explicit edges with [Matplotlib pcolormesh](https://matplotlib.org/stable/api/_as_gen/matplotlib.axes.Axes.pcolormesh.html).

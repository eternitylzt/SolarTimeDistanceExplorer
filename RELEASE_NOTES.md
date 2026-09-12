# Solar Time–Distance Explorer 1.2.3

Auto colors moved immediately before Selected. Frame-marker text can be edited
or restored in the style dialog. New frame selections reset custom text.

Auto colors 移至 Selected 前；帧标记支持编辑多行文字及恢复默认。
本次发布包含源码、测试及各平台构建基础；Windows 完整程序见 GitHub Release。

Frame markers: clear, edit line/text styles, drag labels, double-click to edit.
OLS automatically estimates acceleration independently of label visibility;
the separate acceleration mode is removed from the UI. Details always retain
the estimate, uncertainty (when available) and quadratic residuals.

帧标记可清除、设置线条/文字样式、拖动与双击编辑。多点拟合自动估算加速度，
可选显示；取消独立加速度模式。数值、误差与二次拟合残差保留在详情中。

This release adds background/cancellable quality scans, safe TD plot shapes,
retained OLS picks with 1σ bands, optional constant acceleration, plot-to-image
frame selection, compact Region controls and copyable source locations.
No new third-party dependencies.

本版新增：后台质量报告、绘图区形状修正、多点拟合选点/误差阴影、可选恒定加速度、
选帧跳转、区域布局与当前路径查看。

## 中文

本版本沿用现有依赖：

- 数据质量报告：时间、曝光、WCS、观测者信息与距离换算依据。
- Slit/Region 编辑撤销与重做，独立于绘图历史。
- `.stdsession` 分析会话：结果、速度标记、样式、视图与历史；不复制原始 FITS。
- 缓存数组内存预算与性能统计；直方图复用坐标轴/图形。
- 多点 OLS/分段速度拟合、统计标准误与可复制的选点/残差详情。
- 可选观测缺口留白、区域有效像素/角面积检查、全序列共享直方图 bins。
- 图像/数值导出统一记录参数和数据来源，TD FITS 保留64位浮点精度。

新增用法与科学限制见 [ResearchTools.md](docs/ResearchTools.md)。

### 1.1 功能保留

- 未开始落点时更换 Slit/Region 形状，保留原名称与编号。
- 绘图历史使用独立窗口，准确保留每次 TD、区域趋势及直方图序列，不覆盖当前绘制状态。
- 已删除、参数已改变或其他数据源的标记仅供历史查看；匹配的当前标记可显式选回继续分析。关闭历史或点击“回到最新状态”即可继续当前操作。
- Help 新增 Check for Updates...：仅手动检查，显示新版并打开对应 Release 页面，或提示已是最新版/网络错误。不自动下载、安装或后台检查。
- About 增加 Releases 下载链接。没有新增第三方依赖，继续支持中英文和多平台。

## English

No new third-party dependencies.

- Data quality reports, marker undo/redo, portable analysis sessions.
- Byte-budgeted frame caches, performance statistics and lighter histogram updates.
- Multipoint OLS/segmented velocity fits, standard errors and auditable residuals.
- Optional observational-gap blanks, valid coverage/area diagnostics and shared histogram bins.
- Unified figure/numerical provenance and float64 TD FITS exports.

### Retained from 1.1

- Changing an unstarted Slit/Region shape preserves its name and identifier.
- Independent history windows retain each TD, Region trend, histogram, and histogram sequence without replacing the current analysis or drawing state.
- Deleted, scientifically changed, or other-dataset markers remain view-only. Matching current markers can be explicitly selected for further analysis. Close history or choose Return to Latest State to resume.
- Help → Check for Updates... manually checks the latest version and opens its Release page, with clear up-to-date and network-error feedback. No background checks, automatic downloads, or installation.
- About now links directly to Releases. No additional third-party dependencies; bilingual and cross-platform support retained.

Windows x64 is the primary tested platform. Linux and macOS builds are native, unsigned packages produced by GitHub-hosted runners.

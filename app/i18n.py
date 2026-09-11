"""Small runtime language layer for the Chinese/English desktop interface.

The application stores one language code and applies it before any window is
constructed. A Qt event filter also translates dialogs and status text created
later by existing scientific modules, which keeps the language choice global
without coupling data/plotting code to Qt translation catalogs.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QEvent, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QDoubleSpinBox,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QWidget,
)

_language = "zh"


def set_language(code: str) -> None:
    global _language
    _language = "en" if str(code).lower().startswith("en") else "zh"


def language() -> str:
    return _language


def tr(chinese: str, english: str) -> str:
    return english if _language == "en" else chinese


_PHRASES = {
    "Solar Time–Distance Explorer — 主要功能": "Solar Time–Distance Explorer — Features",
    "切片/区域绘制与科学参数说明": "Slit/Region Drawing and Scientific Parameters",
    "当前数据缓存已清除；已显示的帧仍保留，下一次访问其他帧时会重新读取/处理。":
        "The current data cache was cleared. The displayed frame remains; other frames will be read/processed again when requested.",
    "同时保留的完整帧/已配准 Map 数量（AIA 单帧可能占用数十 MB）：":
        "Full-resolution/prepared Map frames retained in memory (one AIA frame can use tens of MB):",
    "默认保存当前视图中的全部信息；以下选项可以独立组合。":
        "The complete current view is saved by default; the following options can be combined.",
    "这些数值控制绘图区在画布中的边距与多子图间距；应用后会关闭自动布局，并为该页面持久保存。":
        "These values control canvas margins and subplot spacing. Applying them disables automatic layout and saves them for this page.",
    "Percentile 使用下方百分位；Manual 使用 vmin/vmax；Min–Max 和 ZScale 自动计算。":
        "Percentile uses the limits below; Manual uses vmin/vmax; Min–Max and ZScale are automatic.",
    "在 Map 上用半透明带显示实际参与法向统计的 Slit 宽度。":
        "Show the scientific Slit width as a translucent band on the Map.",
    "单击保存当前页；点右侧箭头可明确选择 Map、TD 或区域图。":
        "Click to save the current page; use the arrow to explicitly choose Map, TD, or Region Analysis.",
    "SciPy 可以读取 IDL SAVE 文件，但没有符合标准的 writesav 写入接口。请导出为 FITS/CSV/TXT；这些格式无需 IDL 即可完整保存数值结果。":
        "SciPy can read IDL SAVE files but provides no standards-compliant writesav API. Export FITS/CSV/TXT instead.",
    "所选 SAV 变量不是标准 SSW Map 结构体（DATA/XC/YC/DX/DY）；图像数据仍可使用，但坐标轴为像素。":
        "The selected SAV variable is not a standard SSW Map structure (DATA/XC/YC/DX/DY). The image remains usable with pixel axes.",
    "该变量是数值图像，但不是标准 SSW Map 结构体（DATA/XC/YC/DX/DY）。当前使用像素坐标显示。":
        "This is a numeric image but not a standard SSW Map structure (DATA/XC/YC/DX/DY); pixel coordinates are used.",
    "请选择 NumPy 数组中的时间维：": "Select the time dimension of the NumPy array:",
    "Left 必须小于 Right，Bottom 必须小于 Top。": "Left must be below Right, and Bottom below Top.",
    "请打开单幅 FITS、FITS 文件夹/数据立方或 IDL SAV 数据。":
        "Open a FITS image, FITS folder/cube, or IDL SAV dataset.",
    "当前显示的坐标范围": "Current visible coordinate range",
    "完整直方图范围": "Full histogram range",
    "完整图像范围": "Full image range",
    "当前窗口分辨率": "Current viewport resolution",
    "原始图像分辨率": "Original image resolution",
    "显示坐标轴与刻度": "Include axes and ticks",
    "显示实际观测时间": "Include observation time",
    "显示图像标题": "Include title",
    "显示已勾选 Slit": "Include checked Slits",
    "显示已勾选 Region": "Include checked Regions",
    "显示 Legend": "Include legend",
    "显示 Grid": "Include grid",
    "显示 Colorbar": "Include colorbar",
    "MP4 编码器": "MP4 Codec",
    "区域直方图动画导出设置": "Region Histogram Animation Export",
    "动画导出设置": "Animation Export Settings",
    "保存当前视图设置": "Save Current View Settings",
    "时间轴设置": "Time Axis Configuration",
    "需要设置时间": "Time Configuration Required",
    "调整子图布局": "Configure Subplots",
    "内存缓存设置": "Memory Cache Settings",
    "打开单幅 FITS 图像…": "Open FITS Image…",
    "打开 FITS 文件夹…": "Open FITS Folder…",
    "打开三维 FITS 数据立方…": "Open 3-D FITS Cube…",
    "打开 IDL SAV…": "Open IDL SAV…",
    "打开项目…": "Open Project…",
    "保存项目…": "Save Project…",
    "保存当前视图…": "Save Current View…",
    "保存 Map 图像…": "Save Map Figure…",
    "保存 Time–Distance 图…": "Save Time–Distance Figure…",
    "保存区域分析图…": "Save Region Analysis Figure…",
    "当前 FITS 元数据…": "Current FITS Metadata…",
    "打开日志文件夹": "Open Log Folder",
    "主要功能简介": "Feature Overview",
    "切换切片/区域页时保留已勾选标记": "Keep checked overlays when switching Slit/Region tabs",
    "内存缓存帧数…": "Memory Cache Frames…",
    "清除当前数据缓存": "Clear Current Data Cache",
    "设置历史记录条数…": "Set History Limit…",
    "清除绘图历史": "Clear Plot History",
    "导出 GIF / MP4…": "Export GIF / MP4…",
    "导出 GIF / MP4": "Export GIF / MP4",
    "导出数值数据…": "Export Numerical Data…",
    "导出图像…": "Export Figure…",
    "导出最近一次区域数据…": "Export Latest Region Data…",
    "导出直方图动画…": "Export Histogram Animation…",
    "导出时距数据": "Export Time–Distance Data",
    "绘制已勾选区域的时间变化": "Plot Checked Region Trends",
    "绘制当前帧直方图": "Plot Current-Frame Histogram",
    "绘制范围直方图序列": "Build Histogram Sequence",
    "使用 TD 当前时间范围": "Use Current TD Time Range",
    "横轴标题包含起始时间": "Include Start Time in X Label",
    "Legend 与标题同字号": "Match Legend and Title Size",
    "测量速度": "Measure Velocity",
    "清除斜率标记": "Clear Velocity Markers",
    "文件(&F)": "File(&F)",
    "查看(&V)": "View(&V)",
    "动画(&A)": "Animation(&A)",
    "时距图(&T)": "Time–Distance(&T)",
    "设置(&S)": "Settings(&S)",
    "帮助(&H)": "Help(&H)",
    "保存科研图像": "Save Scientific Figure",
    "绘图历史": "Plot History",
    "暂无绘图历史": "No Plot History",
    "语言 / Language": "Language",
    "中文": "Chinese",
    "常用操作": "Common Actions",
    "数据集摘要": "Dataset Summary",
    "尚未载入数据。": "No dataset loaded.",
    "图像显示": "Image Display",
    "区域分析": "Region Analysis",
    "数据集": "Dataset",
    "图像": "Image",
    "切片": "Slits",
    "区域": "Regions",
    "动画": "Animation",
    "退出": "Exit",
    "关于": "About",
    "新建切片": "New Slit",
    "生成时距图": "Generate Time–Distance",
    "播放/暂停": "Play/Pause",
    "◀ 上一帧": "◀ Previous",
    "▶ 播放": "▶ Play",
    "⏸ 暂停": "⏸ Pause",
    "下一帧 ▶": "Next ▶",
    "帧：—": "Frame: —",
    "时间：—": "Time: —",
    "参考帧": "Reference Frame",
    "预览帧率": "Preview FPS",
    "Normalization（显示范围）": "Normalization",
    "显示可拖动标签": "Show draggable label",
    "名称": "Name",
    "线条颜色": "Line Color",
    "显示线宽": "Display Line Width",
    "标签文字颜色": "Label Text Color",
    "标签背景颜色": "Label Background",
    "标签文字大小": "Label Text Size",
    "统计量": "Statistic",
    "直方图 bin 宽度": "Histogram Bin Width",
    "时间变化形式": "Trend Plot Type",
    "直方图形式": "Histogram Plot Type",
    "直方图纵轴": "Histogram Y Axis",
    "帧范围": "Frame Range",
    "播放帧率": "Playback FPS",
    "像素坐标": "Pixel Coordinates",
    "世界坐标/WCS": "World Coordinates / WCS",
    "固定像素位置": "Fixed Pixel Position",
    "固定世界坐标": "Fixed World Coordinate",
    "太阳自转跟踪（实验）": "Solar-Rotation Tracking (Experimental)",
    "像素固定": "Pixel Fixed",
    "世界坐标固定": "World-Coordinate Fixed",
    "均值": "Mean",
    "总和": "Sum",
    "柱状图": "Bar",
    "线状图": "Line",
    "计数 Count": "Count",
    "相对频率 Frequency": "Relative Frequency",
    "分辨率": "Resolution",
    "图像范围": "View Range",
    "宽度": "Width",
    "高度": "Height",
    "帧率": "FPS",
    "起始帧": "Start Frame",
    "结束帧": "End Frame",
    "序列起始帧": "Sequence Start",
    "序列结束帧": "Sequence End",
    "帧步长": "Frame Step",
    "码率": "Bitrate",
    "自定义": "Custom",
    "时间轴": "Time Axis",
    "使用帧序号": "Use Frame Index",
    "起始时间 + 固定间隔": "Start Time + Fixed Cadence",
    "轴 0": "Axis 0",
    "轴 1": "Axis 1",
    "轴 2": "Axis 2",
    "左边距 Left": "Left Margin",
    "右边界 Right": "Right Margin",
    "下边距 Bottom": "Bottom Margin",
    "上边界 Top": "Top Margin",
    "水平子图间距 WSpace": "Horizontal Spacing",
    "垂直子图间距 HSpace": "Vertical Spacing",
    "复位": "Home",
    "恢复完整视野": "Reset original view",
    "后退": "Back",
    "返回上一个视野": "Return to previous view",
    "前进": "Forward",
    "前往下一个视野": "Go to next view",
    "平移": "Pan",
    "拖动平移视野": "Drag to pan",
    "框选放大": "Zoom to Rectangle",
    "拖动矩形框放大子区域": "Drag a rectangle to zoom",
    "布局": "Subplots",
    "保存 Map": "Save Map",
    "保存当前 Map 图像": "Save the current Map figure",
    "时间刻度": "Time Ticks",
    "时:分:秒": "HH:MM:SS",
    "时:分": "HH:MM",
    "年-月-日 时:分:秒": "YYYY-MM-DD HH:MM:SS",
    "坐标标题字号": "Axis Label Size",
    "刻度字号": "Tick Size",
    "取消": "Cancel",
    "文本": "Text",
    "高": "High",
    "低": "Low",
    "不确定": "Uncertain",
    "近似均匀": "Nearly Uniform",
    "不均匀": "Irregular",
    "（无）": "(None)",
    "圆形": "Circle",
    "长方形": "Rectangle",
    "形状": "Shape",
    "预览": "Preview",
    "选择颜色": "Choose Color",
    "无法启动": "Unable to Start",
    "当前元数据": "Current Metadata",
    "NaN/图外": "NaN / Outside Image",
    " 帧": " frames",
    " 位": " digits",
    "变量：": "Variable:",
    "切换语言": "Switch Language",
    "布局参数无效": "Invalid Layout",
    "手动设置闭合区域": "Define Closed Region Manually",
    "中心 X [pixel]": "Centre X [pixel]",
    "中心 Y [pixel]": "Centre Y [pixel]",
    "圆半径 [pixel]": "Circle Radius [pixel]",
    "长方形宽度 [pixel]": "Rectangle Width [pixel]",
    "长方形高度 [pixel]": "Rectangle Height [pixel]",
    "旋转角 [deg]": "Rotation Angle [deg]",
    "UTC 起始时间（ISO）": "UTC Start Time (ISO)",
    "时间间隔 [s]": "Cadence [s]",
    "选择速度线颜色": "Choose Velocity Line Color",
    "选择速度标注文字颜色": "Choose Velocity Label Color",
    "选择速度标注背景颜色": "Choose Velocity Label Background",
    "手动区域参数无效": "Invalid Manual Region Parameters",
    "无法计算区域直方图": "Unable to Calculate Region Histogram",
    "无法导出区域直方图动画": "Unable to Export Region Histogram Animation",
    "闭合区域分析失败": "Closed-Region Analysis Failed",
    "无法打开 FITS 图像": "Unable to Open FITS Image",
    "无法打开 FITS 文件夹": "Unable to Open FITS Folder",
    "无法打开 FITS 数据立方": "Unable to Open FITS Cube",
    "无法打开 IDL SAV": "Unable to Open IDL SAV",
    "无法保存 Map 图像": "Unable to Save Map Figure",
    "无法导出时距图": "Unable to Export Time–Distance Figure",
    "无法保存区域分析图": "Unable to Save Region Figure",
    "无法导出时距数据": "Unable to Export Time–Distance Data",
    "无法保存项目": "Unable to Save Project",
    "无法打开项目": "Unable to Open Project",
    "时间设置无效": "Invalid Time Configuration",
    "时距图生成失败": "Time–Distance Generation Failed",
    "导出区域直方图动画": "Export Region Histogram Animation",
    "保存区域分析图": "Save Region Analysis Figure",
    "保存 Map 图像": "Save Map Figure",
    "导出时距图": "Export Time–Distance Figure",
    "导出时距数值数据": "Export Time–Distance Numerical Data",
    "导出区域数据": "Export Region Data",
    "打开 FITS 文件夹": "Open FITS Folder",
    "打开单幅 FITS 图像": "Open FITS Image",
    "打开三维 FITS 数据立方": "Open 3-D FITS Cube",
    "打开 IDL SAV": "Open IDL SAV",
    "打开项目": "Open Project",
    "保存项目": "Save Project",
    "选择图像变量": "Select Image Variable",
    "可选的 SAV 时间变量": "Available SAV Time Variables",
    "坐标 / Map 信息": "Coordinate / Map Information",
}

_REPLACEMENTS = sorted(_PHRASES.items(), key=lambda item: len(item[0]), reverse=True)


def translate_text(value: str) -> str:
    """Translate exact UI phrases and dynamic Chinese message fragments."""
    if _language != "en" or not value:
        return value
    if value in _PHRASES:
        return _PHRASES[value]
    translated = value
    dynamic = {
        "正在读取 FITS 时间/WCS：": "Reading FITS time/WCS: ",
        "正在准备 FITS 文件夹扫描…": "Preparing FITS folder scan…",
        "正在准备首帧图像与 WCS…": "Preparing first image and WCS…",
        "正在准备首帧图像与 WCS…": "Preparing first frame and WCS…",
        "正在计算闭合区域的时间变化…": "Calculating region trends…",
        "正在计算区域直方图序列…": "Calculating region histogram sequence…",
        "正在渲染区域直方图动画…": "Rendering region histogram animation…",
        "正在生成时距图…": "Generating time–distance diagram…",
        "正在导出动画…": "Exporting animation…",
        "已生成并缓存 ": "Generated and cached ",
        " 帧区域直方图序列。": " histogram frames.",
        "区域直方图动画已保存：": "Region histogram animation saved: ",
        "动画已保存：": "Animation saved: ",
        "时距图已保存：": "Time–distance figure saved: ",
        "区域分析图已保存：": "Region analysis figure saved: ",
        "当前图像已保存：": "Current image saved: ",
        "区域数据已保存：": "Region data saved: ",
        "时距数据已保存：": "Time–distance data saved: ",
        "项目已保存：": "Project saved: ",
        "项目已恢复：": "Project restored: ",
        "区域直方图动画导出已取消。": "Region histogram movie export cancelled.",
        "区域直方图序列计算已取消。": "Region histogram sequence calculation cancelled.",
        "区域分析已取消。": "Region analysis cancelled.",
        "时距图生成已取消。": "Time–distance generation cancelled.",
        "绘图历史已清除。": "Plot history cleared.",
        "请先生成帧范围直方图序列。": "Build a frame-range histogram sequence first.",
        "请至少勾选一个已完成的闭合区域。": "Check at least one completed closed region.",
        "请先生成时距图，再缩放到所需时间范围。": "Generate and zoom a time–distance diagram first.",
        "请先绘制区域时间变化或直方图。": "Plot a region trend or histogram first.",
        "请先计算区域时间变化或直方图。": "Calculate a region trend or histogram first.",
        "请先加载数据，再选择切片。": "Load a dataset before selecting a slit.",
        "请先加载图像或序列，再绘制区域。": "Load an image or sequence before drawing a region.",
        "请先选择并完成一个活动切片。": "Select and finish an active slit first.",
        "请先在 Slit 列表中选择要删除的切片。": "Select the slit to delete in the Slit list.",
        "当前没有可清除的数据缓存。": "There is no current dataset cache to clear.",
        "区域直方图动画正在导出。": "A region histogram movie is already exporting.",
        "切片至少需要两个点。": "A slit requires at least two points.",
        "当前区域的控制点数量不足。": "The current region does not have enough control points.",
        "时间间隔必须是以秒为单位的数值。": "Cadence must be a numeric value in seconds.",
        "未找到标准 SSW Map 结构体或二维/三维数值图像变量。": "No standard SSW Map structure or 2-D/3-D numeric image variable was found.",
        "参考帧没有可靠 WCS": "The reference frame has no reliable WCS",
        "Slit 列表状态异常；请重新选择切片。": "The Slit list state is inconsistent; select a slit again.",
        "区域列表状态异常；请重新选择区域。": "The Region list state is inconsistent; select a region again.",
        "已取消切片绘制。": "Slit drawing cancelled.",
        "已取消区域绘制。": "Region drawing cancelled.",
        "直线切片：依次左键单击起点和终点。": "Line slit: left-click the start and end points.",
        "折线切片：左键添加点；在原地双击或单击右键完成。": "Polyline slit: left-click points; double-click in place or right-click to finish.",
        "平滑曲线：左键添加控制点；在原地双击或单击右键完成。": "Smooth curve: left-click control points; double-click in place or right-click to finish.",
        "圆形：左键单击圆心，移动预览半径，再次单击完成。": "Circle: left-click the centre, preview the radius, and click again to finish.",
        "长方形：左键单击一条边的两个端点，移动预览高度，第三次单击完成。": "Rectangle: click two edge points, preview the height, then click a third time.",
        "多边形：左键添加顶点；在原地双击或单击右键完成。": "Polygon: left-click vertices; double-click in place or right-click to finish.",
        "自定义函数目前仅为实验性扩展接口，尚未提供交互工具。": "Custom Function is an experimental extension point without an interactive tool yet.",
        "无法打开": "Unable to open",
        "无法保存": "Unable to save",
        "无法导出": "Unable to export",
        "已取消": "Cancelled",
        "请先": "Please first ",
        "帧：": "Frame: ",
        "时间：": "Time: ",
        "像素：x=": "Pixel: x=",
        "；数值=": "; Value=",
        "；世界坐标=(": "; World=(",
        "已删除切片 ": "Deleted slit ",
        "参考帧已设为第 ": "Reference frame set to frame ",
        "已采用 TD 当前可见范围：": "Using the current visible TD range: ",
        "已计算 ": "Calculated ",
        " 个区域的": " regions: ",
        "时间变化。": " trend.",
        " 个距离采样 × ": " distance samples × ",
        " 个时刻。": " time samples.",
        "已从 ": "Loaded ",
        "；已清除上一数据集缓存": "; previous dataset cache cleared",
        "加载 ": " loaded ",
    }
    for source, target in sorted(dynamic.items(), key=lambda item: len(item[0]), reverse=True):
        translated = translated.replace(source, target)
    for source, target in _REPLACEMENTS:
        translated = translated.replace(source, target)
    return translated


class LanguageEventFilter(QObject):
    """Translate newly shown widgets and later text updates in English mode."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._busy = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802
        if _language != "en" or self._busy:
            return False
        event_type = event.type()
        if event_type in {QEvent.Type.Show, QEvent.Type.Polish} and isinstance(watched, QWidget):
            self.localize(watched)
        elif event_type == QEvent.Type.Paint and isinstance(
            watched, (QLabel, QAbstractButton, QGroupBox, QMenu, QStatusBar, QDialog)
        ):
            self._translate_one(watched)
        return False

    def localize(self, root: QWidget) -> None:
        self._busy = True
        try:
            self._translate_one(root)
            for child in root.findChildren(QObject):
                self._translate_one(child)
        finally:
            self._busy = False

    @staticmethod
    def _set_if_changed(obj: Any, getter: str, setter: str) -> None:
        old = getattr(obj, getter)()
        new = translate_text(old)
        if new != old:
            getattr(obj, setter)(new)

    def _translate_one(self, obj: QObject) -> None:
        if isinstance(obj, QAction):
            self._set_if_changed(obj, "text", "setText")
            self._set_if_changed(obj, "toolTip", "setToolTip")
            return
        if isinstance(obj, QDialog):
            self._set_if_changed(obj, "windowTitle", "setWindowTitle")
        if isinstance(obj, QToolBar):
            self._set_if_changed(obj, "windowTitle", "setWindowTitle")
        if isinstance(obj, QMenu):
            self._set_if_changed(obj, "title", "setTitle")
        elif isinstance(obj, QGroupBox):
            self._set_if_changed(obj, "title", "setTitle")
        elif isinstance(obj, (QLabel, QAbstractButton)):
            self._set_if_changed(obj, "text", "setText")
        elif isinstance(obj, QLineEdit):
            self._set_if_changed(obj, "placeholderText", "setPlaceholderText")
        elif isinstance(obj, (QSpinBox, QDoubleSpinBox)):
            self._set_if_changed(obj, "prefix", "setPrefix")
            self._set_if_changed(obj, "suffix", "setSuffix")
        elif isinstance(obj, QStatusBar):
            message = obj.currentMessage()
            translated = translate_text(message)
            if translated != message:
                obj.showMessage(translated)
        if isinstance(obj, QComboBox):
            for index in range(obj.count()):
                old = obj.itemText(index); new = translate_text(old)
                if new != old:
                    obj.setItemText(index, new)
        if isinstance(obj, QTabWidget):
            for index in range(obj.count()):
                old = obj.tabText(index); new = translate_text(old)
                if new != old:
                    obj.setTabText(index, new)

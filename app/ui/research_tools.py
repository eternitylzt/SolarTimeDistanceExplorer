"""Advanced research/session tools kept out of the basic drawing workflow."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QInputDialog, QLabel, QPushButton, QMenu, QProgressDialog
from app.ui.quality_worker import QualityWorker
from app.i18n import tr
from app.data.factory import open_from_descriptor
from app.data.quality import quality_report
from app.paths.base import PathGeometry
from app.regions.base import RegionGeometry
from app.project.serializer import project_payload
from app.project.session import save_session, load_session
from app.processing.provenance import result_provenance, write_sidecar
from app.ui.dialogs import HelpTextDialog, show_error
from app.ui.edit_history import MarkerUndo


class ResearchToolsMixin:
    """Optional tools using the same live data model and publication canvases."""

    def _init_research_tools(self) -> None:
        self.edit_history = MarkerUndo(self)
        existing_menus = [a.menu() for a in self.menuBar().actions() if a.menu() is not None]
        settings_menu = next(m for m in existing_menus if self.cache_size_action in m.actions())
        help_menu = next(m for m in existing_menus if self.about_action in m.actions())
        edit_menu = QMenu(tr("编辑(&E)", "Edit(&E)"),self.menuBar())
        self.menuBar().insertMenu(self.menuBar().actions()[1],edit_menu)
        undo = QAction(tr("撤销标记编辑", "Undo marker edit"), self)
        undo.setShortcut(QKeySequence.StandardKey.Undo); undo.triggered.connect(self.edit_history.undo)
        redo = QAction(tr("重做标记编辑", "Redo marker edit"), self)
        redo.setShortcuts([QKeySequence.StandardKey.Redo, QKeySequence("Ctrl+Shift+Z")]); redo.triggered.connect(self.edit_history.redo)
        edit_menu.addActions([undo, redo])
        quality = QPushButton(tr("数据质量报告…", "Data Quality Report…"))
        quality.clicked.connect(self.show_quality_report)
        self.dataset_panel.layout().insertWidget(1, quality)
        self.quality_summary = QLabel(); self.quality_summary.setWordWrap(True)
        self.dataset_panel.layout().insertWidget(2, self.quality_summary)
        self.cache_label = QLabel(); self.statusBar().addPermanentWidget(self.cache_label)
        self.cache_budget_mb = int(self.settings.value("cache_budget_mb", 512))
        self._timings: dict[str, list[float]] = {}
        file_menu = self.menuBar().actions()[0].menu()
        file_menu.addSeparator()
        file_menu.addAction(tr("保存分析会话…", "Save Analysis Session…"), self.save_analysis_session)
        file_menu.addAction(tr("打开分析会话…", "Open Analysis Session…"), self.open_analysis_session)
        settings_menu.addAction(tr("缓存内存预算…", "Cache Memory Budget…"), self.configure_cache_budget)
        settings_menu.addAction(tr("性能统计…", "Performance Statistics…"), self.show_performance)
        self._quality_worker = None
        self._draw_started = None
        self.image_canvas.mpl_connect("draw_event", lambda _event: self._record_draw_timing())
        self._quality_cache = None
        from app.ui.frame_picker import PlotFramePicker
        self._td_frame_picker = PlotFramePicker(self, self.td_canvas, self.td_canvas.toolbar, lambda: self.td_result)
        self._region_frame_picker = PlotFramePicker(self, self.region_canvas, self.region_navigation, lambda: self.region_result)

    def _marker_edit_state(self) -> dict[str, Any]:
        return {"paths": [p.to_dict() for p in self.paths], "regions": [r.to_dict() for r in self.regions],
            "active_path_id": self.active_path_id, "active_region_id": self.active_region_id,
            "next_slit": self._next_slit_number, "next_region": self._next_region_number,
            "path_drawing": self.path_editor.drawing, "region_drawing": self.region_editor.drawing}

    def _restore_marker_edit_state(self, state: dict[str, Any]) -> None:
        self.path_editor.set_geometry(None); self.region_editor.set_geometry(None)
        self.paths = [PathGeometry.from_dict(p) for p in state["paths"]]
        self.regions = [RegionGeometry.from_dict(r) for r in state["regions"]]
        self.active_path_id = state.get("active_path_id")
        self.active_region_id = state.get("active_region_id")
        self._next_slit_number = state.get("next_slit", 1); self._next_region_number = state.get("next_region", 1)
        for widget, geometries, active in ((self.path_panel.paths, self.paths, self.active_path_id),
                                          (self.region_panel.regions, self.regions, self.active_region_id)):
            widget.blockSignals(True)
            try:
                widget.clear()
                for geometry in geometries:
                    widget.addItem(self._marker_item(geometry.name, geometry.visible, geometry.id))
                widget.setCurrentRow(next((i for i, g in enumerate(geometries) if g.id == active), -1))
            finally:
                widget.blockSignals(False)
        path, region = self.active_path(), self.active_region()
        if path is not None:
            self._load_path_settings(path)
        if region is not None:
            self._load_region_settings(region)
        self.path_editor.set_enabled(self.left_tabs.currentIndex() == 2)
        self.region_editor.set_enabled(self.left_tabs.currentIndex() == 3)
        if self.path_editor.enabled:
            self.path_editor.set_geometry(path)
            if path is not None and state.get("path_drawing"):
                self.path_editor.begin_geometry(path)
        if self.region_editor.enabled:
            self.region_editor.set_geometry(region)
            if region is not None and state.get("region_drawing"):
                self.region_editor.begin_geometry(region)
        self._refresh_overlays(); self._apply_region_result_visibility()

    def _research_dataset_installed(self) -> None:
        if self._quality_worker is not None:
            self._quality_worker.requestInterruption()
        self._quality_cache = None; self._timings.clear()
        self.edit_history.reset()
        setter = getattr(self.dataset, "set_cache_budget", None)
        if setter:
            setter(self.cache_budget_mb)
        missing_exposure = sum(m.exposure_seconds is None or not np.isfinite(m.exposure_seconds) or m.exposure_seconds<=0
                               for m in (self.dataset.get_frame_metadata(i) for i in range(self.dataset.n_frames)))
        dt = np.diff(self.dataset.times.unix) if self.dataset.times is not None else np.array([])
        invalid_time = int(np.count_nonzero(dt<=0))
        self.quality_summary.setText(tr(
            f"质量提示：曝光缺失/无效 {missing_exposure} 帧；重复/逆序时间 {invalid_time} 处。km/Mm 使用名义投影尺度，详情见报告。",
            f"Quality: missing/invalid exposure in {missing_exposure} frames; duplicate/reversed times: {invalid_time}. km/Mm use a nominal projected scale; see report."))
        self._update_cache_status()

    def show_quality_report(self) -> None:
        if self.dataset is None:
            return
        if self._quality_cache is None:
            if self._quality_worker is not None:
                return
            worker = QualityWorker(self.dataset, self)
            self._quality_worker = worker
            progress = QProgressDialog(tr("检查头信息…", "Checking headers…"), tr("取消", "Cancel"), 0, self.dataset.n_frames, self)
            progress.setMinimumDuration(0)
            progress.canceled.connect(worker.requestInterruption)
            worker.progress.connect(lambda done, total: progress.setValue(done))
            def ready(report):
                if self.dataset is worker.dataset and not worker.isInterruptionRequested():
                    self._quality_cache = report
                    progress.close()
                    self.show_quality_report()
            def finished():
                progress.close(); progress.deleteLater()
                self._quality_worker = None
                worker.deleteLater()
            worker.ready.connect(ready)
            worker.failed.connect(lambda error: self.statusBar().showMessage(error, 15000))
            worker.finished.connect(finished)
            worker.start()
            return
        report = self._quality_cache
        labels = {
            "frames": "帧数", "time_header_fields": "时间头字段", "time_axis": "时间轴来源",
            "missing_individual_times": "未逐帧记录时间数（立方/SAV 可另有时间数组）",
            "duplicate_time_intervals": "重复时间间隔数", "reversed_time_intervals": "逆序时间间隔数",
            "median_positive_cadence_s": "正时间间隔中位数 [s]", "large_gap_after_frame_1based": "大缺口前的帧号（>5倍中位间隔）",
            "missing_or_invalid_exposure": "曝光时间缺失/无效帧数", "missing_angular_wcs": "缺少可用角度 WCS 的帧数",
            "missing_observer_distance": "观测者距离缺失帧数", "distance_conversion": "距离转换依据", "wcs_validation": "WCS 检查范围",
        }
        text = "\n\n".join(f"{tr(labels.get(k,k), k)}: {v}" for k,v in report.items())
        text += tr("\n\n注意：WCS 可解析不代表指向已校准。缺失观测者信息时，SunPy 可能假定地球视角。名义尺度换算不是实际太阳表面速度；不要把统计拟合误差当成全部物理误差。",
                   "\n\nParseable WCS does not guarantee pointing accuracy. SunPy may assume an Earth observer when metadata are missing. Fit standard errors exclude projection and calibration systematics.")
        HelpTextDialog(tr("数据质量报告", "Data Quality Report"), text, self).exec()

    def configure_cache_budget(self) -> None:
        value, ok = QInputDialog.getInt(self, tr("缓存内存预算", "Cache Memory Budget"),
            tr("缓存数组上限 [MiB]（不含 GUI、计算结果和原始 SAV 立方）：", "Cached array budget [MiB] (excludes GUI, results and raw SAV cubes):"), self.cache_budget_mb, 32, 16384, 64)
        if ok:
            self.cache_budget_mb = value; self.settings.setValue("cache_budget_mb", value)
            setter = getattr(self.dataset, "set_cache_budget", None)
            if setter:
                setter(value)
            self._update_cache_status()

    def _update_cache_status(self) -> None:
        stats = getattr(self.dataset, "cache_stats", lambda: {})()
        if stats:
            self.cache_label.setText(f"Cache ≤ {stats['bytes']/1024**2:.0f} / {stats['budget']/1024**2:.0f} MiB")
            self.cache_label.setToolTip(tr("保守计数；不含当前显示/计算结果。", "Conservative payload accounting; excludes current display/results."))
        else:
            self.cache_label.setText("")

    def _record_timing(self, name: str, seconds: float) -> None:
        values = self._timings.setdefault(name, [])
        values.append(seconds*1000); del values[:-100]

    def _record_draw_timing(self) -> None:
        from time import perf_counter
        if self._draw_started is not None:
            self._record_timing("Image render including queued draw", perf_counter()-self._draw_started)
            self._draw_started = None

    def show_performance(self) -> None:
        stats = getattr(self.dataset, "cache_stats", lambda: {})()
        lines = [f"{name}: median {np.median(values):.1f} ms; p95 {np.percentile(values,95):.1f} ms; n={len(values)}"
                 for name,values in self._timings.items() if values]
        text = "\n".join(lines) + "\n\nCache: " + json.dumps(stats)
        HelpTextDialog(tr("性能统计（最近100次）", "Performance Statistics (last 100)"), text, self).exec()

    def _analysis_session_state(self) -> dict[str, Any]:
        return {"project": project_payload(self.dataset, self.paths, self.active_path_id, self.reference_frame,
                    self._image_settings(), self._td_settings(), self.regions),
            "times": self.dataset.times, "time_origin": self.dataset.time_origin,
            "source_shape": self.dataset.shape, "source_n_frames": self.dataset.n_frames,
            "source_identity": result_provenance(self.dataset,{})["source_files"],
            "markers": self._marker_edit_state(), "current_frame": self.current_frame,
            "main_tab": self.main_tabs.currentIndex(), "left_tab": self.left_tabs.currentIndex(),
            "td": self.td_result, "region": self._full_region_result,
            "histograms": self._region_hist_sequence, "histogram_position": self._region_hist_position,
            "history": self._history_entries, "velocity_measurements": self.td_canvas.measurement_snapshot(),
            "viewports": {key: [canvas.axes.get_xlim(), canvas.axes.get_ylim()] for key,canvas in
                (("image",self.image_canvas),("td",self.td_canvas),("region",self.region_canvas))},
            "gap_options": [self.td_show_gaps.isChecked(), self.td_gap_factor.value()]}

    def save_analysis_session(self) -> None:
        if self.dataset is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, tr("保存分析会话", "Save Analysis Session"), "analysis.stdsession", "STDE Session (*.stdsession)")
        if not path:
            return
        try:
            save_session(path, self._analysis_session_state())
            self.statusBar().showMessage(tr("分析结果、标注和历史已保存（不复制原始 FITS）。", "Results, annotations and history saved; original FITS data are not copied."), 8000)
        except Exception as exc:
            show_error(self, tr("会话保存失败", "Session save failed"), str(exc))

    def _restore_analysis_session(self, state: dict[str, Any]) -> None:
        descriptor = dict(state["project"]["dataset"])
        if not Path(descriptor["source"]).exists():
            if descriptor["source_type"] == "fits_folder":
                replacement = QFileDialog.getExistingDirectory(self, tr("定位原始 FITS 文件夹", "Locate Original FITS Folder"))
            else:
                replacement, _ = QFileDialog.getOpenFileName(self, tr("定位原始数据", "Locate Original Data"))
            if not replacement:
                raise FileNotFoundError("Original data are required to resume a session.")
            descriptor["source"] = replacement
        dataset = open_from_descriptor(descriptor)
        times = state.get("times")
        if (times is not None and len(times) != dataset.n_frames) or (
            state.get("source_n_frames",dataset.n_frames)!=dataset.n_frames or
            tuple(state.get("source_shape",dataset.shape)) != tuple(dataset.shape)):
            dataset.close()
            raise ValueError("Source frame count/shape differs from the saved session. Open the source as a new dataset.")
        originals = state.get("source_identity",[])
        current_files = result_provenance(dataset,{})["source_files"]
        if originals and (len(originals)!=len(current_files) or any(
            a.get("size_bytes") != b.get("size_bytes") or a.get("mtime_ns") != b.get("mtime_ns")
            for a,b in zip(originals,current_files))):
            dataset.close()
            raise ValueError("Source files changed since this session was saved (size/mtime). Open the source as a new dataset to reanalyse.")
        dataset.set_times(times); dataset.time_origin = state.get("time_origin", "session")
        self._timer.stop(); self._region_hist_timer.stop()
        self._install_dataset(dataset)
        self.reference_frame = max(0,min(int(state["project"].get("reference_frame",0)),dataset.n_frames-1))
        self.dataset_panel.reference.setValue(self.reference_frame)
        self.left_tabs.setCurrentIndex(state.get("left_tab",0))
        self.edit_history.restore(state["markers"])
        self._apply_image_settings(state["project"].get("display_settings",{}))
        self._apply_td_settings(state["project"].get("td_display_settings",{}))
        self.td_show_gaps.setChecked(state.get("gap_options",[False,5])[0])
        self.td_gap_factor.setValue(state.get("gap_options",[False,5])[1])
        self.td_result = state.get("td"); self._redraw_td()
        if self.td_result is not None:
            self.td_canvas.restore_measurements(state.get("velocity_measurements",[]))
        sequence = state.get("histograms")
        if sequence is not None:
            self._install_region_histogram_sequence(sequence,state.get("histogram_position",0),record=False)
        else:
            self._full_region_result = state.get("region"); self._apply_region_result_visibility()
        self.set_current_frame(state.get("current_frame",0))
        self._history_entries = state.get("history",[])[:self.history_limit]
        self._history_marker_ids = {m for e in self._history_entries for m in e.get("marker_ids",[])}
        self._rebuild_history_menu()
        self.main_tabs.setCurrentIndex(state.get("main_tab",0))
        for key,canvas in (("image",self.image_canvas),("td",self.td_canvas),("region",self.region_canvas)):
            if key in state.get("viewports",{}):
                x,y = state["viewports"][key]; canvas.axes.set_xlim(x); canvas.axes.set_ylim(y); canvas.draw_idle()
        self._capture_region_histogram_viewport()
        self.edit_history.reset()

    def open_analysis_session(self) -> None:
        path,_ = QFileDialog.getOpenFileName(self,tr("打开分析会话", "Open Analysis Session"),filter="STDE Session (*.stdsession)")
        if path:
            try:
                self._restore_analysis_session(load_session(path))
            except Exception as exc:
                show_error(self,tr("会话恢复失败", "Session restore failed"),str(exc))

    def _figure_provenance(self, canvas: Any, options: dict) -> dict[str, Any]:
        if canvas is self.td_canvas and self.td_result is not None:
            metadata = dict(self.td_result.metadata)
            metadata["velocity_measurements"] = self.td_canvas.measurement_snapshot()
            metadata["display"] = self._td_plot_options(self.td_result)
        elif canvas is self.region_canvas and self.region_result is not None:
            metadata = dict(self.region_result.metadata)
            metadata["display"] = self._region_plot_options(self.region_result, self._region_hist_sequence)
            metadata["region_ids"] = self.region_result.region_ids
            metadata["frame_index"] = getattr(self.region_result,"frame_index",None)
        elif self.dataset is not None:
            metadata = result_provenance(self.dataset,{"frame":self.current_frame,"display":self._image_settings(),
                "slits":[p.to_dict() for p in self.paths],"regions":[r.to_dict() for r in self.regions]})
        else:
            metadata = {}
        return {**metadata, "figure_export":options,"xlim":canvas.axes.get_xlim(),"ylim":canvas.axes.get_ylim()}

    def research_help_text(self) -> str:
        return tr(
            "数据质量：报告仅读取头信息，不修改数据。重复时间需要先修正，不能用真实时间 TD 隐藏问题。km/Mm 使用名义投影尺度，非真实三维距离。\n\n"
            "撤销/重做：Ctrl+Z、Ctrl+Shift+Z（Windows 也可 Ctrl+Y），针对 Slit/Region 编辑；历史查看与撤销相互独立。文字输入框保留自身撤销功能。连续拖拽/参数调整合并为一次操作。\n\n"
            "分析会话：文件菜单保存 .stdsession，包括结果、标注、绘图历史和视图，不复制原始图像。轻量 .stdproj 仍只存数据引用与参数。会话压缩包只含 JSON/NPY，不使用 pickle。\n\n"
            "速度：Two points 保留两点模式；OLS fit 多次单击沿结构选点，右键/双击/Enter 完成，Escape 取消。Segmented 为相邻点逐段测速。显示 ±1σ 拟合标准误（至少3点），只反映等方差独立残差，不含人工描迹/WCS/投影误差。数据导出和图像 sidecar 保存选点、残差。\n\n"
            "观测缺口：勾选 Show gaps 后，超过阈值×中位 cadence 的间隔显示空白，不补数据。阈值不是仪器曝光时间。\n\n"
            "区域覆盖：导出附带有限值像素数、视场内 mask 像素数与近似角面积；不会自动补偿缺失区域。有效像素变化时请谨慎解释 Sum。直方图序列所有帧/区域共享 bins，频率为各 bin 占有效像素的比例。\n\n"
            "缓存：内存预算仅约束缓存数组，不是整个进程内存。当前图像、SAV 原始立方和分析结果另占内存。性能统计记录最近100次读取及重绘耗时，用于定位瓶颈。",
            "Data quality reports inspect headers without changing data. Duplicate times must be corrected for true-time TD. km/Mm use a nominal projected scale, not 3-D distance.\n\n"
            "Undo/Redo applies to Slit/Region edits, separately from plot history. Text fields retain text undo. Continuous gestures are coalesced.\n\n"
            "File > Save Analysis Session stores results, annotations, history and viewports in .stdsession without original image cubes. .stdproj remains lightweight. Archives use JSON/NPY, never pickle.\n\n"
            "Velocity: Two points, OLS fit or Segmented. For multiple points, right-click/double-click/Enter finishes, Escape cancels. ±1 sigma is residual-based OLS standard error (3+ points); tracing, WCS and projection systematics are excluded. Picked points and residuals are exported in sidecars.\n\n"
            "Show gaps inserts blank intervals above a multiple of median cadence; it does not infer exposure or fill missing data.\n\n"
            "Region exports include finite-pixel counts, in-FOV mask counts and approximate angular area. No missing-area correction is applied. Interpret Sum cautiously when coverage changes. Histogram sequences share bins; relative frequency divides by finite-pixel counts.\n\n"
            "Cache budgets constrain cached arrays, not GUI/results/raw SAV cubes. Performance statistics separate the last 100 read and rendering timings.")

    def show_fit_details(self) -> None:
        """Expose original picked points/residuals without cluttering the TD plot."""
        index = int(self.slope_selection.currentData() or 0)
        groups = self.td_canvas.measurement_snapshot()
        if index>0 and not self.slope_auto_colors.isChecked():
            groups = [g for g in groups if g["index"]==index]
        text = tr("OLS 假定时间无误差、距离误差独立且同方差。±值为1σ拟合标准误，非总物理误差。选点 x 是当前图的 Matplotlib 日期数（天）或帧坐标。\n\n",
                  "OLS assumes exact times and independent equal-variance distance errors. ± is 1-sigma fit standard error, not total physical uncertainty. Picked x is Matplotlib date number (days) or frame coordinate.\n\n")
        for g in groups:
            text += f"v_{g['index']} | {g.get('fit_method','two-point')} | Δt={g['delta_t']:.6g}; Δs={g['delta_s']:.6g}; slope stderr={g.get('stderr')}\n"
            if g.get("acceleration") is not None:
                text += self.td_canvas._acceleration_text(g).replace("$", "") + "\n"
                text += f"Acceleration (native): {g['acceleration']:.12g} {g.get('distance_unit','')}/{g.get('slope_time_unit','s')}²; 1-sigma error: {g.get('acceleration_stderr')}\n"
                if g.get("acceleration_stderr") is None:
                    text += tr("三点仅确定二次曲线，没有剩余自由度估计误差。\n", "Three points determine a quadratic but leave no residual degrees of freedom to estimate uncertainty.\n")
                text += tr("恒定加速度假设：仅适用于整体持续加速/减速；请检查轨迹与残差。\n", "Constant acceleration assumes overall speeding up/slowing down; inspect trajectory and residuals.\n")
                text += "Quadratic residuals: " + str(g.get("acceleration_residuals", [])) + "\n"
            elif g.get("acceleration_reason"):
                text += "Acceleration unavailable: " + g["acceleration_reason"] + "\n"
            text += "x, distance, residual\n"
            for point,residual in zip(g.get("points",[]),g.get("residuals",[])):
                text += f"{point[0]:.12g}, {point[1]:.9g}, {residual:.9g}\n"
            text += "\n"
        HelpTextDialog(tr("速度拟合详情（可复制）", "Velocity Fit Details (copyable)"),text,self).exec()

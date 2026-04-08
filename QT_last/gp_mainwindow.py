from PyQt5.QtWidgets import (QMainWindow, QLabel, QVBoxLayout, QWidget,
                             QHBoxLayout, QAction, QSplitter,
                             QFileDialog, QInputDialog)
from PyQt5.QtCore import Qt, QTimer

import gp_cameradisplaywidget
import gp_detectiondisplaywidget
import gp_chartwidget
import gp_globals


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("工业齿轮实时检测系统")
        self.setGeometry(50, 50, 1400, 800)

        # ---- 菜单栏 ----
        self._create_menu_bar()

        # ---- 中央布局 ----
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 标题
        title = QLabel("工业齿轮实时目标检测系统")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 24px; font-weight: bold; color: #ffffff;
            padding: 15px; background-color: #2c3e50;
            border-radius: 8px; margin-bottom: 10px;
        """)
        root.addWidget(title)

        # 主内容区(QSplitter上下分割)
        splitter = QSplitter(Qt.Vertical)

        # ---- 上半部分: 摄像头 + 检测面板 ----
        top_widget = QWidget()
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)

        # 左: 摄像头
        cam_layout = QVBoxLayout()
        self.camera1 = gp_cameradisplaywidget.CameraDisplayWidget(4)
        self.camera2 = gp_cameradisplaywidget.CameraDisplayWidget(2)
        cam_layout.addWidget(self.camera1)
        cam_layout.addWidget(self.camera2)
        top_layout.addLayout(cam_layout)

        # 中: 检测结果
        self.detection_display = gp_detectiondisplaywidget.DetectionDisplayWidget()
        top_layout.addWidget(self.detection_display)

        # 右: 统计图表
        self.chart_widget = gp_chartwidget.StatsChartWidget()
        self.chart_widget.setMinimumWidth(300)
        top_layout.addWidget(self.chart_widget)

        splitter.addWidget(top_widget)

        # ---- 下半部分: 检测历史 ----
        self.history_widget = gp_chartwidget.DetectionHistoryWidget()
        splitter.addWidget(self.history_widget)

        splitter.setSizes([500, 250])
        root.addWidget(splitter)

        # 状态栏
        self.status_label = QLabel("准备启动摄像头...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("""
            color: #666; padding: 10px; background-color: #ecf0f1;
            border-radius: 5px; margin-top: 5px;
        """)
        root.addWidget(self.status_label)

        # 连接检测结果到图表和历史
        self.detection_display.worker.detection_ready.connect(self._on_detection_for_chart)

        # 图表刷新定时器(每2秒刷新一次)
        self.chart_timer = QTimer()
        self.chart_timer.timeout.connect(self._refresh_chart)
        self.chart_timer.start(2000)

        # 启动摄像头
        self.start_cameras()

    def _create_menu_bar(self):
        """创建菜单栏"""
        menubar = self.menuBar()

        # 文件菜单
        file_menu = menubar.addMenu("文件")

        export_action = QAction("导出检测日志 (Excel)", self)
        export_action.triggered.connect(self._export_log)
        file_menu.addAction(export_action)

        clear_log_action = QAction("清空日志", self)
        clear_log_action.triggered.connect(self._clear_log)
        file_menu.addAction(clear_log_action)

        # 设置菜单
        settings_menu = menubar.addMenu("设置")

        sms_action = QAction("SMS报警配置", self)
        sms_action.triggered.connect(self._configure_sms)
        settings_menu.addAction(sms_action)

        lighting_action = QAction("补光参数", self)
        lighting_action.triggered.connect(self._configure_lighting)
        settings_menu.addAction(lighting_action)

    def start_cameras(self):
        cam1_started = self.camera1.start_camera()
        cam2_started = self.camera2.start_camera()
        if cam1_started and cam2_started:
            self.status_label.setText("摄像头已启动，点击右侧'开始检测'按钮进行YOLO检测")
            self.status_label.setStyleSheet(self.status_label.styleSheet().replace("#666", "#27ae60"))
        else:
            self.status_label.setText("无法启动摄像头，请检查连接")
            self.status_label.setStyleSheet(self.status_label.styleSheet().replace("#666", "#e74c3c"))

    def _on_detection_for_chart(self, result):
        """检测结果同步到历史表"""
        boxes = result.boxes
        if len(boxes) > 0:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            confs = boxes.conf.cpu().numpy()
            names = result.names
            for i, cls_id in enumerate(cls_ids):
                cn = names[cls_id]
                action_map = {"good": "进入分类", "miss": "剔除", "bad": "剔除", "well": "放行"}
                self.history_widget.add_record(
                    class_name=cn,
                    confidence=float(confs[i]),
                    action=action_map.get(cn, "-"),
                    stage=gp_globals.detection_stage,
                )

    def _refresh_chart(self):
        """定时刷新统计图表"""
        stats = gp_globals.detection_logger.get_stats()
        if stats["total"] > 0:
            self.chart_widget.update_chart(stats)

    # ---- 菜单动作 ----
    def _export_log(self):
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出检测日志", f"detection_log_{ts}.xlsx", "Excel (*.xlsx)")
        if filepath:
            ok = gp_globals.detection_logger.export_excel(filepath)
            self.status_label.setText(f"日志已导出: {filepath}" if ok else "导出失败")

    def _clear_log(self):
        gp_globals.detection_logger.clear()
        self.history_widget.clear()
        self.chart_widget._init_empty()
        self.status_label.setText("日志已清空")

    def _configure_sms(self):
        phone, ok = QInputDialog.getText(self, "SMS配置", "报警手机号:")
        if ok and phone:
            gp_globals.sms_manager.phone_number = phone
            threshold, ok2 = QInputDialog.getInt(
                self, "SMS配置", "连续缺陷报警阈值:", 5, 1, 100)
            if ok2:
                gp_globals.sms_manager.alert_threshold = threshold
            self.status_label.setText(f"SMS已配置: {phone}, 阈值={gp_globals.sms_manager.alert_threshold}")

    def _configure_lighting(self):
        target, ok = QInputDialog.getInt(
            self, "补光配置", "目标亮度 (0-255):",
            gp_globals.lighting_controller.target, 0, 255)
        if ok:
            gp_globals.lighting_controller.target = target
            self.status_label.setText(f"补光目标亮度已设为: {target}")

    def closeEvent(self, event):
        gp_globals.running = False
        self.camera1.stop_camera()
        self.camera2.stop_camera()
        self.detection_display.stop_detection_thread()
        event.accept()

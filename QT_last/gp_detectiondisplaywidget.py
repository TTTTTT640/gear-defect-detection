import os
import threading
from datetime import datetime
from PyQt5.QtWidgets import (QLabel, QVBoxLayout, QWidget, QHBoxLayout,
                             QTextEdit, QPushButton, QComboBox, QFileDialog)
from PyQt5.QtCore import Qt, QTimer

from gp_detectionworker import DetectionWorker
import gp_globals
import gp_serial


class DetectionDisplayWidget(QWidget):
    """右侧显示检测结果的控件"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.send_debounce = 0

        self.setMinimumSize(640, 480)
        self.setStyleSheet("border: 2px solid #cccccc; background-color: #f8f9fa;")

        layout = QVBoxLayout(self)

        # 防抖定时器
        self.timer = QTimer()
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.on_timer_timeout)
        self.timer3 = QTimer()
        self.timer3.setSingleShot(True)
        self.timer3.timeout.connect(self.on_timer3_timeout)

        # 标题
        title = QLabel("YOLO检测结果")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 18px; font-weight: bold; color: #2c3e50;
            padding: 10px; background-color: #e8f4f8;
            border-radius: 5px; margin: 5px;
        """)
        layout.addWidget(title)

        # 模型切换 + 推理后端显示
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("推理后端:"))
        self.backend_label = QLabel(gp_globals.backend1.get_info())
        self.backend_label.setStyleSheet("color: #8e44ad; font-size: 12px;")
        model_layout.addWidget(self.backend_label)
        model_layout.addStretch()

        model_layout.addWidget(QLabel("阶段1模型:"))
        self.model1_combo = QComboBox()
        self._populate_model_combo(self.model1_combo)
        model_layout.addWidget(self.model1_combo)

        model_layout.addWidget(QLabel("阶段2模型:"))
        self.model2_combo = QComboBox()
        self._populate_model_combo(self.model2_combo)
        model_layout.addWidget(self.model2_combo)

        self.apply_model_btn = QPushButton("切换模型")
        self.apply_model_btn.clicked.connect(self.apply_model_switch)
        self.apply_model_btn.setStyleSheet("""
            QPushButton { background: #8e44ad; color: white; border: none;
                         padding: 4px 8px; border-radius: 3px; }
            QPushButton:hover { background: #7d3c98; }
        """)
        model_layout.addWidget(self.apply_model_btn)
        layout.addLayout(model_layout)

        # 结果显示区域
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            QTextEdit {
                font-family: 'Consolas', 'Monaco', monospace; font-size: 14px;
                background-color: white; border: 1px solid #bdc3c7;
                border-radius: 5px; padding: 10px;
            }
        """)
        layout.addWidget(self.result_text)

        # 统计信息 + 亮度显示
        stats_layout = QHBoxLayout()
        self.stats_label = QLabel("等待检测结果...")
        self.stats_label.setStyleSheet("""
            color: #27ae60; font-size: 14px; font-weight: bold;
            padding: 5px; background-color: #ecf0f1; border-radius: 3px;
        """)
        stats_layout.addWidget(self.stats_label, 3)

        self.brightness_label = QLabel("亮度: -- | PWM: --%")
        self.brightness_label.setStyleSheet("color: #f39c12; font-size: 12px; padding: 5px;")
        stats_layout.addWidget(self.brightness_label, 1)
        layout.addLayout(stats_layout)

        # 检测频率控制
        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("检测频率:"))
        self.freq_slider = QPushButton("正常 (0.1s)")
        self.freq_slider.clicked.connect(self.toggle_frequency)
        self.freq_slider.setStyleSheet("""
            QPushButton { background-color: #3498db; color: white;
                         border: none; padding: 5px; border-radius: 3px; }
        """)
        self.detection_interval = 0.1
        freq_layout.addWidget(self.freq_slider)
        freq_layout.addStretch()
        layout.addLayout(freq_layout)

        # 控制按钮
        button_layout = QHBoxLayout()
        btn_style = """
            QPushButton {{ background-color: {bg}; color: white; border: none;
                          padding: 8px; border-radius: 3px; font-weight: bold; }}
            QPushButton:hover {{ background-color: {hover}; }}
        """
        self.detect_btn = QPushButton("开始检测")
        self.detect_btn.clicked.connect(self.toggle_detection)
        self.detect_btn.setStyleSheet(btn_style.format(bg="#3498db", hover="#2980b9"))

        self.clear_btn = QPushButton("清空结果")
        self.clear_btn.clicked.connect(self.clear_results)
        self.clear_btn.setStyleSheet(btn_style.format(bg="#95a5a6", hover="#7f8c8d"))

        self.export_btn = QPushButton("导出Excel")
        self.export_btn.clicked.connect(self.export_excel)
        self.export_btn.setStyleSheet(btn_style.format(bg="#27ae60", hover="#229954"))

        button_layout.addWidget(self.detect_btn)
        button_layout.addWidget(self.export_btn)
        button_layout.addWidget(self.clear_btn)
        layout.addLayout(button_layout)

        # 创建工作线程对象
        self.worker = DetectionWorker()
        self.worker.detection_ready.connect(self.update_detection_display)
        self.worker.stats_updated.connect(self.stats_label.setText)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.brightness_updated.connect(self.update_brightness)

        self.detection_enabled = False
        self.worker_thread = None

    # ---- 模型管理 ----
    def _populate_model_combo(self, combo):
        """扫描目录中的.pt文件填充下拉框"""
        base = os.path.dirname(os.path.abspath(__file__))
        for f in sorted(os.listdir(base)):
            if f.endswith(".pt"):
                combo.addItem(f)

    def apply_model_switch(self):
        """切换推理模型"""
        from gp_inference_backend import create_backend
        base = os.path.dirname(os.path.abspath(__file__))
        m1 = os.path.join(base, self.model1_combo.currentText())
        m2 = os.path.join(base, self.model2_combo.currentText())
        try:
            gp_globals.backend1 = create_backend(gp_globals.BACKEND_TYPE, m1)
            gp_globals.backend2 = create_backend(gp_globals.BACKEND_TYPE, m2)
            self.backend_label.setText(gp_globals.backend1.get_info())
            self.stats_label.setText(f"模型已切换: {self.model1_combo.currentText()} / {self.model2_combo.currentText()}")
        except Exception as e:
            self.show_error(f"模型切换失败: {e}")

    # ---- 定时器回调 ----
    def on_timer_timeout(self):
        self.send_debounce = 0
        if gp_globals.conveyor_running == 0:
            gp_globals.conveyor_running = 1
            gp_serial.serial_manager.send("07")

    def on_timer3_timeout(self):
        gp_globals.pass_debounce = 0
        if gp_globals.conveyor_running == 0:
            gp_globals.conveyor_running = 1
            gp_serial.serial_manager.send("07")

    # ---- 频率切换 ----
    def toggle_frequency(self):
        if self.detection_interval == 0.1:
            self.detection_interval = 0.3
            self.freq_slider.setText("低速 (0.3s)")
        elif self.detection_interval == 0.3:
            self.detection_interval = 0.5
            self.freq_slider.setText("更慢 (0.5s)")
        else:
            self.detection_interval = 0.1
            self.freq_slider.setText("正常 (0.1s)")
        # 同步到worker
        self.worker.detection_interval = self.detection_interval

    # ---- 检测控制 ----
    def toggle_detection(self):
        self.detection_enabled = not self.detection_enabled
        if self.detection_enabled:
            self.detect_btn.setText("停止检测")
            self.detect_btn.setStyleSheet(self.detect_btn.styleSheet().replace("#3498db", "#e74c3c"))
            self.start_detection_thread()
        else:
            self.detect_btn.setText("开始检测")
            self.detect_btn.setStyleSheet(self.detect_btn.styleSheet().replace("#e74c3c", "#3498db"))
            self.stop_detection_thread()

    def start_detection_thread(self):
        gp_globals.running = True
        self.worker.detection_interval = self.detection_interval
        self.worker_thread = threading.Thread(target=self.worker.start_detection)
        self.worker_thread.daemon = True
        self.worker_thread.start()

    def stop_detection_thread(self):
        gp_globals.running = False
        self.worker.stop_detection()
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)

    # ---- 亮度显示 ----
    def update_brightness(self, brightness, pwm):
        self.brightness_label.setText(f"亮度: {brightness:.0f} | PWM: {pwm}%")

    # ---- 检测结果处理(状态机 + 日志 + SMS) ----
    def update_detection_display(self, result):
        """更新检测结果显示 + 写日志 + 检查SMS报警
        状态机:
          阶段0 "good" → 进入阶段1，停传送带
          阶段0 "miss" → 剔除02
          阶段1 "bad"  → 剔除02，回阶段0
          阶段1 "well" → 放行01，回阶段0
        """
        boxes = result.boxes
        if len(boxes) == 0:
            self.result_text.setText("未检测到目标")
            return

        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        names = result.names
        logger = gp_globals.detection_logger

        display_text = "检测到的目标：\n" + "=" * 40 + "\n"

        for i, cls_id in enumerate(cls_ids):
            class_name = names[cls_id]
            confidence = confs[i]
            display_text += f"  {class_name}: {confidence:.2%}\n"

            serial_cmd = None

            # --- 阶段0: 齿轮存在性检测 ---
            if class_name == "good" and self.send_debounce == 0 and gp_globals.detection_stage == 0:
                if gp_globals.conveyor_running == 1:
                    gp_globals.conveyor_running = 0
                    gp_serial.serial_manager.send("08")
                gp_globals.detection_stage = 1
                self.send_debounce = 1
                self.timer.start(2300)
                serial_cmd = "08"

            elif class_name == "miss" and self.send_debounce == 0:
                gp_serial.serial_manager.send("02")
                if gp_globals.conveyor_running == 1:
                    gp_serial.serial_manager.send("08")
                    gp_globals.conveyor_running = 0
                gp_globals.detection_stage = 0
                self.send_debounce = 1
                self.timer.start(2300)
                serial_cmd = "02"

            # --- 阶段1: 齿轮缺陷分类 ---
            if class_name == "bad" and self.send_debounce == 0 and gp_globals.detection_stage == 1:
                gp_globals.defect_confirmed = 0
                gp_serial.serial_manager.send("02")
                if gp_globals.conveyor_running == 1:
                    gp_serial.serial_manager.send("08")
                    gp_globals.conveyor_running = 0
                gp_globals.detection_stage = 0
                self.send_debounce = 1
                self.timer.start(2300)
                serial_cmd = "02"

            if class_name == "well" and gp_globals.pass_debounce == 0 and gp_globals.detection_stage == 1:
                gp_serial.serial_manager.send("01")
                gp_globals.defect_confirmed = 1
                gp_globals.detection_stage = 0
                gp_globals.pass_debounce = 1
                self.timer3.start(2300)
                serial_cmd = "01"

            # 写日志
            if serial_cmd:
                logger.log_detection(
                    stage=gp_globals.detection_stage,
                    class_name=class_name,
                    confidence=float(confidence),
                    serial_cmd=serial_cmd,
                )
                # SMS报警检查
                gp_globals.sms_manager.check_alert(logger.consecutive_defects)

        self.result_text.setText(display_text)

    # ---- 导出Excel ----
    def export_excel(self):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"detection_log_{ts}.xlsx"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出检测日志", default_name, "Excel文件 (*.xlsx)")
        if filepath:
            ok = gp_globals.detection_logger.export_excel(filepath)
            if ok:
                self.stats_label.setText(f"日志已导出: {filepath}")
            else:
                self.stats_label.setText("导出失败，请检查openpyxl是否安装")

    # ---- 其他 ----
    def clear_results(self):
        self.result_text.clear()
        self.stats_label.setText("结果已清空")
        with gp_globals.results_lock:
            gp_globals.detection_results = None

    def show_error(self, error_msg):
        self.stats_label.setText(f"错误: {error_msg}")
        self.stats_label.setStyleSheet(self.stats_label.styleSheet().replace("#27ae60", "#e74c3c"))

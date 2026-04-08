"""
PC模拟测试版 - 工业齿轮缺陷检测系统
用于在Windows PC上测试检测效果，无需V3开发板和串口硬件。

用法:
  python pc_test.py --camera 0          # 使用Windows摄像头(默认)
  python pc_test.py --video gear.mp4    # 使用视频文件
  python pc_test.py --image gear.jpg    # 使用单张图片
"""

import os
import sys
import time
import argparse
import threading
import numpy as np

import cv2
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QVBoxLayout,
                             QWidget, QHBoxLayout, QTextEdit, QPushButton, QFileDialog)
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal

from ultralytics import YOLO

# ============================================================
#  全局配置
# ============================================================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL1_PATH = os.path.join(_BASE_DIR, "best.pt")
MODEL2_PATH = os.path.join(_BASE_DIR, "final2.pt")

# ============================================================
#  串口模拟 (MockSerialManager)
# ============================================================
SERIAL_COMMANDS = {
    "07": "启动传送带",
    "08": "停止传送带",
    "01": "合格放行",
    "02": "缺陷剔除",
}

class MockSerialManager:
    """模拟串口管理器，仅打印指令，不实际发送"""
    def __init__(self):
        self.log = []

    def send(self, data):
        desc = SERIAL_COMMANDS.get(data, f"未知指令({data})")
        msg = f"[SERIAL] {data} -> {desc}"
        print(msg)
        self.log.append((time.time(), data, desc))
        return True

    def connect(self):
        print("[SERIAL] 模拟串口已连接")
        return True

    def close(self):
        print("[SERIAL] 模拟串口已关闭")

serial_manager = MockSerialManager()

# ============================================================
#  全局状态
# ============================================================
frame_lock = threading.Lock()
results_lock = threading.Lock()
current_frame = None
detection_results = None
running = True

# 状态机
conveyor_running = 0    # 传送带: 0=停, 1=运行
defect_confirmed = 0
pass_debounce = 0
detection_stage = 0     # 0=存在性检测, 1=缺陷分类

# ============================================================
#  摄像头线程
# ============================================================
class CameraThread(QThread):
    frame_ready = pyqtSignal(object)
    error_occurred = pyqtSignal(str)

    def __init__(self, source):
        super().__init__()
        self.source = source
        self.running = True
        self._is_image = False

    def run(self):
        global current_frame

        # 判断输入源类型
        if isinstance(self.source, str) and os.path.isfile(self.source):
            ext = os.path.splitext(self.source)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png', '.bmp'):
                self._is_image = True
                frame = cv2.imread(self.source)
                if frame is None:
                    self.error_occurred.emit(f"无法读取图片: {self.source}")
                    return
                while self.running:
                    self.frame_ready.emit(frame.copy())
                    with frame_lock:
                        current_frame = frame.copy()
                    self.msleep(100)
                return

        # 视频文件或摄像头
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            self.error_occurred.emit(f"无法打开视频源: {self.source}")
            return

        while self.running:
            ret, frame = cap.read()
            if not ret:
                if isinstance(self.source, str):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # 视频循环播放
                    continue
                self.msleep(10)
                continue
            self.frame_ready.emit(frame.copy())
            with frame_lock:
                current_frame = frame.copy()

        cap.release()

    def stop(self):
        self.running = False
        self.wait()

# ============================================================
#  检测工作线程
# ============================================================
class DetectionWorker:
    def __init__(self, model1, model2):
        self.model1 = model1
        self.model2 = model2
        self.running = False
        self.detection_enabled = False
        self.on_result = None     # callback(result, stage, inference_ms)
        self.on_stats = None      # callback(text)
        self.on_error = None      # callback(text)

    def start(self):
        self.running = True
        self.detection_enabled = True
        self._loop()

    def stop(self):
        self.running = False
        self.detection_enabled = False

    def _loop(self):
        global conveyor_running, detection_stage

        print("检测线程已启动")
        if conveyor_running == 0:
            serial_manager.send("07")
            conveyor_running = 1

        while self.running and self.detection_enabled:
            frame = None
            with frame_lock:
                if current_frame is not None:
                    frame = current_frame.copy()

            if frame is not None:
                try:
                    t0 = time.time()
                    if detection_stage == 0:
                        results = self.model1(frame, show=False, verbose=False, conf=0.6)
                    else:
                        results = self.model2(frame, show=False, verbose=False, conf=0.7)
                    inference_ms = (time.time() - t0) * 1000

                    result = results[0]
                    with results_lock:
                        detection_results = result

                    if self.on_result:
                        self.on_result(result, detection_stage, inference_ms)

                    boxes = result.boxes
                    if len(boxes) > 0:
                        if conveyor_running == 1:
                            serial_manager.send("08")
                            conveyor_running = 0
                        cls_ids = boxes.cls.cpu().numpy().astype(int)
                        names = result.names
                        class_counts = {}
                        for cid in cls_ids:
                            n = names[cid]
                            class_counts[n] = class_counts.get(n, 0) + 1
                        total = len(boxes)
                        stats = " | ".join([f"{n}: {c}" for n, c in class_counts.items()])
                        if self.on_stats:
                            self.on_stats(f"检测到 {total} 个目标 | {stats} | {inference_ms:.0f}ms")
                    else:
                        if self.on_stats:
                            self.on_stats(f"未检测到目标 | {inference_ms:.0f}ms")

                except Exception as e:
                    if self.on_error:
                        self.on_error(str(e))

            time.sleep(0.1)

        serial_manager.send("08")
        conveyor_running = 0
        print("检测线程已结束")


# ============================================================
#  主窗口
# ============================================================
class MainWindow(QMainWindow):
    _update_result_signal = pyqtSignal(object, int, float)
    _update_stats_signal = pyqtSignal(str)
    _update_error_signal = pyqtSignal(str)

    def __init__(self, source, model1, model2):
        super().__init__()
        self.setWindowTitle("齿轮检测 - PC模拟测试")
        self.setGeometry(100, 100, 1100, 650)

        self._update_result_signal.connect(self._on_detection_result)
        self._update_stats_signal.connect(self._on_stats)
        self._update_error_signal.connect(self._on_error)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 标题
        title = QLabel("工业齿轮缺陷检测系统 - PC模拟模式")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("""
            font-size: 22px; font-weight: bold; color: #fff;
            padding: 12px; background-color: #2c3e50;
            border-radius: 8px; margin-bottom: 8px;
        """)
        root.addWidget(title)

        # 内容区: 左=摄像头, 右=检测结果
        body = QHBoxLayout()

        # 左侧: 摄像头画面
        left = QVBoxLayout()
        self.camera_label = QLabel("等待画面...")
        self.camera_label.setFixedSize(640, 480)
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setStyleSheet("border: 2px solid #ccc; background: #222;")
        left.addWidget(self.camera_label)

        self.fps_label = QLabel("FPS: --  |  推理: --ms  |  阶段: 0")
        self.fps_label.setStyleSheet("color: #2ecc71; font-size: 13px; font-weight: bold; padding: 4px;")
        left.addWidget(self.fps_label)
        body.addLayout(left)

        # 右侧: 检测结果
        right = QVBoxLayout()
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setStyleSheet("""
            font-family: Consolas, monospace; font-size: 13px;
            background: white; border: 1px solid #bdc3c7;
            border-radius: 5px; padding: 8px;
        """)
        right.addWidget(self.result_text)

        self.stats_label = QLabel("等待检测...")
        self.stats_label.setStyleSheet("color: #27ae60; font-size: 13px; font-weight: bold; padding: 4px;")
        right.addWidget(self.stats_label)

        # 按钮
        btn_layout = QHBoxLayout()
        self.detect_btn = QPushButton("开始检测")
        self.detect_btn.clicked.connect(self.toggle_detection)
        self.detect_btn.setStyleSheet("""
            QPushButton { background: #3498db; color: white; border: none;
                         padding: 8px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #2980b9; }
        """)

        self.screenshot_btn = QPushButton("截图保存")
        self.screenshot_btn.clicked.connect(self.save_screenshot)
        self.screenshot_btn.setStyleSheet("""
            QPushButton { background: #9b59b6; color: white; border: none;
                         padding: 8px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #8e44ad; }
        """)

        self.serial_log_btn = QPushButton("查看串口日志")
        self.serial_log_btn.clicked.connect(self.show_serial_log)
        self.serial_log_btn.setStyleSheet("""
            QPushButton { background: #95a5a6; color: white; border: none;
                         padding: 8px 16px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background: #7f8c8d; }
        """)

        btn_layout.addWidget(self.detect_btn)
        btn_layout.addWidget(self.screenshot_btn)
        btn_layout.addWidget(self.serial_log_btn)
        right.addLayout(btn_layout)
        body.addLayout(right)

        root.addLayout(body)

        # 状态栏
        self.status_label = QLabel(f"输入源: {source}")
        self.status_label.setStyleSheet("color: #666; padding: 6px; background: #ecf0f1; border-radius: 4px;")
        root.addWidget(self.status_label)

        # 启动摄像头
        self.source = source
        self.camera_thread = CameraThread(source)
        self.camera_thread.frame_ready.connect(self._update_camera)
        self.camera_thread.error_occurred.connect(self._on_camera_error)
        self.camera_thread.start()

        # 检测工作器
        self.model1 = model1
        self.model2 = model2
        self.worker = DetectionWorker(model1, model2)
        self.worker.on_result = lambda r, s, ms: self._update_result_signal.emit(r, s, ms)
        self.worker.on_stats = lambda t: self._update_stats_signal.emit(t)
        self.worker.on_error = lambda e: self._update_error_signal.emit(e)
        self.worker_thread = None
        self.detection_on = False

        # FPS计算
        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)
        self._last_inference_ms = 0
        self._last_stage = 0

    # --- 摄像头 ---
    def _update_camera(self, frame):
        self._frame_count += 1
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            640, 480, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.camera_label.setPixmap(pixmap)

    def _on_camera_error(self, msg):
        self.camera_label.setText(f"摄像头错误: {msg}")
        self.status_label.setText(f"错误: {msg}")

    # --- 检测 ---
    def toggle_detection(self):
        if not self.detection_on:
            self.detection_on = True
            self.detect_btn.setText("停止检测")
            self.detect_btn.setStyleSheet(self.detect_btn.styleSheet().replace("#3498db","#e74c3c").replace("#2980b9","#c0392b"))
            self.worker_thread = threading.Thread(target=self.worker.start, daemon=True)
            self.worker_thread.start()
        else:
            self.detection_on = False
            self.detect_btn.setText("开始检测")
            self.detect_btn.setStyleSheet(self.detect_btn.styleSheet().replace("#e74c3c","#3498db").replace("#c0392b","#2980b9"))
            self.worker.stop()

    def _on_detection_result(self, result, stage, inference_ms):
        global detection_stage, conveyor_running, pass_debounce, defect_confirmed
        self._last_inference_ms = inference_ms
        self._last_stage = stage

        boxes = result.boxes
        if len(boxes) == 0:
            self.result_text.setText("未检测到目标")
            return

        cls_ids = boxes.cls.cpu().numpy().astype(int)
        confs = boxes.conf.cpu().numpy()
        names = result.names

        text = "检测到的目标：\n" + "=" * 40 + "\n"
        for i, cid in enumerate(cls_ids):
            cn = names[cid]
            text += f"  {cn}: {confs[i]:.2%}\n"

            # 状态机逻辑 (与V3版一致)
            if cn == "good" and detection_stage == 0:
                if conveyor_running == 1:
                    conveyor_running = 0
                    serial_manager.send("08")
                detection_stage = 1
            elif cn == "miss" and detection_stage == 0:
                serial_manager.send("02")
                if conveyor_running == 1:
                    serial_manager.send("08")
                    conveyor_running = 0
                detection_stage = 0
            elif cn == "bad" and detection_stage == 1:
                serial_manager.send("02")
                if conveyor_running == 1:
                    serial_manager.send("08")
                    conveyor_running = 0
                detection_stage = 0
            elif cn == "well" and detection_stage == 1:
                serial_manager.send("01")
                detection_stage = 0

        self.result_text.setText(text)

    def _on_stats(self, text):
        self.stats_label.setText(text)

    def _on_error(self, text):
        self.stats_label.setText(f"错误: {text}")

    def _update_fps(self):
        fps = self._frame_count
        self._frame_count = 0
        self.fps_label.setText(
            f"FPS: {fps}  |  推理: {self._last_inference_ms:.0f}ms  |  阶段: {self._last_stage}")

    # --- 功能按钮 ---
    def save_screenshot(self):
        with frame_lock:
            if current_frame is not None:
                ts = time.strftime("%Y%m%d_%H%M%S")
                path = os.path.join(_BASE_DIR, f"screenshot_{ts}.jpg")
                cv2.imwrite(path, current_frame)
                self.status_label.setText(f"截图已保存: {path}")

    def show_serial_log(self):
        if not serial_manager.log:
            self.result_text.setText("串口日志为空")
            return
        text = "串口通信日志:\n" + "=" * 40 + "\n"
        for ts, cmd, desc in serial_manager.log[-20:]:
            t = time.strftime("%H:%M:%S", time.localtime(ts))
            text += f"  [{t}] {cmd} -> {desc}\n"
        self.result_text.setText(text)

    # --- 关闭 ---
    def closeEvent(self, event):
        global running
        running = False
        self.worker.stop()
        self.camera_thread.stop()
        event.accept()


# ============================================================
#  入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="齿轮检测PC模拟测试")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--camera", type=int, default=0, help="摄像头编号 (默认0)")
    group.add_argument("--video", type=str, help="视频文件路径")
    group.add_argument("--image", type=str, help="图片文件路径")
    args = parser.parse_args()

    # 确定输入源
    if args.video:
        source = args.video
        print(f"输入源: 视频文件 {source}")
    elif args.image:
        source = args.image
        print(f"输入源: 图片文件 {source}")
    else:
        source = args.camera
        print(f"输入源: 摄像头 {source}")

    # 加载模型
    print(f"加载模型1: {MODEL1_PATH}")
    if not os.path.exists(MODEL1_PATH):
        print(f"警告: 模型文件不存在 {MODEL1_PATH}")
        sys.exit(1)
    model1 = YOLO(MODEL1_PATH)

    print(f"加载模型2: {MODEL2_PATH}")
    if not os.path.exists(MODEL2_PATH):
        print(f"警告: 模型文件不存在 {MODEL2_PATH}")
        sys.exit(1)
    model2 = YOLO(MODEL2_PATH)

    print("模型加载完成，启动GUI...")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow(source, model1, model2)
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

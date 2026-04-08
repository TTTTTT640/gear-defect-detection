import time
from PyQt5.QtCore import pyqtSignal, QObject

import gp_globals
import gp_serial


class DetectionWorker(QObject):
    """工作线程类，用于处理YOLO检测"""
    detection_ready = pyqtSignal(object)     # 检测完成信号
    stats_updated = pyqtSignal(str)          # 统计信息更新信号
    error_occurred = pyqtSignal(str)         # 错误信号
    brightness_updated = pyqtSignal(float, int)  # 亮度信号(brightness, pwm)

    def __init__(self):
        super().__init__()
        self.running = False
        self.detection_enabled = False
        self.detection_interval = 0.1  # 检测间隔(秒)，可从外部设置

    def start_detection(self):
        """开始检测"""
        self.running = True
        self.detection_enabled = True
        self.detection_loop()

    def stop_detection(self):
        """停止检测"""
        self.detection_enabled = False
        self.running = False

    def _run_backend_and_emit(self, current_frame, backend, conf):
        """执行推理并发送结果信号

        Args:
            current_frame: 当前帧
            backend: InferenceBackend实例
            conf: 置信度阈值
        Returns:
            float: 推理耗时(ms)
        """
        t0 = time.time()
        result = backend.predict(current_frame, conf=conf)
        inference_ms = (time.time() - t0) * 1000

        with gp_globals.results_lock:
            gp_globals.detection_results = result
        self.detection_ready.emit(result)

        boxes = result.boxes
        if len(boxes) > 0:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            names = result.names
            class_counts = {}
            for cls_id in cls_ids:
                class_name = names[cls_id]
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
            total = len(boxes)
            stats = " | ".join([f"{name}: {count}" for name, count in class_counts.items()])
            self.stats_updated.emit(f"检测到 {total} 个目标 | {stats} | {inference_ms:.0f}ms")
        else:
            self.stats_updated.emit(f"未检测到目标 | {inference_ms:.0f}ms")

        return inference_ms

    def detection_loop(self):
        """YOLO检测循环（两阶段：存在性检测 → 缺陷分类）"""
        print("YOLO检测线程已启动")
        if gp_globals.conveyor_running == 0:
            gp_serial.serial_manager.send("07")
            gp_globals.conveyor_running = 1

        while self.running and self.detection_enabled:
            current_frame = None
            with gp_globals.frame_lock:
                if gp_globals.frame is not None:
                    current_frame = gp_globals.frame.copy()

            if current_frame is not None:
                try:
                    # 自适应补光：分析帧亮度
                    brightness, pwm = gp_globals.lighting_controller.process_frame(current_frame)
                    self.brightness_updated.emit(brightness, pwm)

                    # 两阶段检测
                    if gp_globals.detection_stage == 0:
                        self._run_backend_and_emit(current_frame, gp_globals.backend1, conf=0.6)
                    elif gp_globals.detection_stage == 1:
                        self._run_backend_and_emit(current_frame, gp_globals.backend2, conf=0.7)

                except Exception as e:
                    self.error_occurred.emit(str(e))

            time.sleep(self.detection_interval)

        gp_serial.serial_manager.send("08")
        gp_globals.conveyor_running = 0
        print("YOLO检测线程结束")

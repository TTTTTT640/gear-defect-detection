import time
from PyQt5.QtCore import pyqtSignal, QObject

import gp_globals 
import gp_serial



class DetectionWorker(QObject):
    """工作线程类，用于处理YOLO检测"""
    detection_ready = pyqtSignal(object)  # 检测完成信号
    stats_updated = pyqtSignal(str)       # 统计信息更新信号
    error_occurred = pyqtSignal(str)      # 错误信号
    
    def __init__(self):
        super().__init__()
        self.running = False
        self.detection_enabled = False

        
        
    def start_detection(self):
        """开始检测"""
        self.running = True
        self.detection_enabled = True
        self.detection_loop()


    
    def stop_detection(self):
        """停止检测"""
        self.detection_enabled = False
        self.running = False
    
    def _run_model_and_emit(self, current_frame, model, conf):
        """执行单次YOLO检测并发送结果信号（消除两阶段重复代码）"""
        results = model(current_frame, show=False, verbose=False, conf=conf)
        with gp_globals.results_lock:
            gp_globals.detection_results = results[0]
        self.detection_ready.emit(results[0])

        boxes = results[0].boxes
        if len(boxes) > 0:
            cls_ids = boxes.cls.cpu().numpy().astype(int)
            if gp_globals.conveyor_running == 1:
                gp_serial.serial_manager.send("08")
                gp_globals.conveyor_running = 0
            names = results[0].names
            class_counts = {}
            for cls_id in cls_ids:
                class_name = names[cls_id]
                class_counts[class_name] = class_counts.get(class_name, 0) + 1
            total = len(boxes)
            stats = " | ".join([f"{name}: {count}" for name, count in class_counts.items()])
            self.stats_updated.emit(f"检测到 {total} 个目标 | {stats}")
        else:
            self.stats_updated.emit("未检测到目标")

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
                print(f"当前检测阶段: {gp_globals.detection_stage}")
                print(f"当前防抖标记: {gp_globals.pass_debounce}")
                try:
                    if gp_globals.detection_stage == 0:
                        print("阶段0: 齿轮存在性检测")
                        self._run_model_and_emit(current_frame, gp_globals.model, conf=0.6)
                    elif gp_globals.detection_stage == 1:
                        print("阶段1: 齿轮缺陷分类")
                        self._run_model_and_emit(current_frame, gp_globals.model2, conf=0.7)





                    
                except Exception as e:
                    self.error_occurred.emit(str(e))

          #  else :
               # gp_serial.serial_manager.send("07")
            
            time.sleep(0.1)  # 控制检测频率
        
        gp_serial.serial_manager.send("08")
        gp_globals.conveyor_running = 0
        print("YOLO检测线程结束")

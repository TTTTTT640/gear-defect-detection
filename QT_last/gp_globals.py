import os
import threading
from ultralytics import YOLO

# ---- 全局变量 ----
frame_lock = threading.Lock()
frame_lock2 = threading.Lock()
results_lock = threading.Lock()
frame = None
frame2 = None

# 模型路径：使用脚本所在目录的相对路径，兼容不同部署环境
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL1_PATH = os.path.join(_BASE_DIR, "best.pt")       # 齿轮存在性检测模型
MODEL2_PATH = os.path.join(_BASE_DIR, "final2.pt")     # 齿轮缺陷分类模型

model = YOLO(MODEL1_PATH)
model2 = YOLO(MODEL2_PATH)

detection_results = None

running = True

# 状态机变量（已重命名以提高可读性）
conveyor_running = 0    # 传送带状态: 0=停止, 1=运行 (原 flag)
defect_confirmed = 0    # 缺陷确认标记 (原 rest2)
pass_debounce = 0       # 合格品防抖标记 (原 rest3)
detection_stage = 0     # 检测阶段: 0=存在性检测, 1=缺陷分类 (原 goodsignal)



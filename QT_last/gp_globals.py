import os
import threading

from gp_inference_backend import create_backend
from gp_logger import DetectionLogger
from gp_sms import MockSmsManager
from gp_lighting import LightingController

# ---- 路径配置 ----
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL1_PATH = os.path.join(_BASE_DIR, "best.pt")       # 齿轮存在性检测模型
MODEL2_PATH = os.path.join(_BASE_DIR, "final2.pt")     # 齿轮缺陷分类模型
DLC_PATH = os.path.join(_BASE_DIR, "gear.dlc")         # NPU DLC模型(预留)
ONNX_PATH = os.path.join(_BASE_DIR, "best.onnx")       # ONNX模型(可选)

# ---- 推理后端配置 ----
# 可选: "cpu"(默认), "onnx", "npu"
# 切换NPU: 拿到Fibo AI Stack SDK后改为 "npu" 并使用 DLC_PATH
BACKEND_TYPE = "cpu"

# 加载推理后端
backend1 = create_backend(BACKEND_TYPE, MODEL1_PATH)   # 阶段0: 存在性检测
backend2 = create_backend(BACKEND_TYPE, MODEL2_PATH)   # 阶段1: 缺陷分类

# ---- 全局模块实例 ----
detection_logger = DetectionLogger()                    # 检测日志
sms_manager = MockSmsManager()                          # SMS报警(PC模式用Mock)
lighting_controller = LightingController(target_brightness=128)  # 自适应补光

# ---- 线程同步 ----
frame_lock = threading.Lock()
results_lock = threading.Lock()
frame = None

detection_results = None
running = True

# ---- 状态机变量 ----
conveyor_running = 0    # 传送带状态: 0=停止, 1=运行
defect_confirmed = 0    # 缺陷确认标记
pass_debounce = 0       # 合格品防抖标记
detection_stage = 0     # 检测阶段: 0=存在性检测, 1=缺陷分类

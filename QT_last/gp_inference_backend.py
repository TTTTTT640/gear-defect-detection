"""
推理后端抽象层 - 支持CPU/ONNX/NPU多种推理方式
拿到Fibo AI Stack SDK后，只需实现NpuBackend.predict()即可切换到NPU推理。
"""

import os
import time


class InferenceBackend:
    """推理后端基类"""

    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None

    def load(self):
        """加载模型"""
        raise NotImplementedError

    def predict(self, frame, conf=0.5):
        """执行推理

        Args:
            frame: BGR numpy数组
            conf: 置信度阈值
        Returns:
            results: 与 ultralytics YOLO results[0] 兼容的结果对象
        """
        raise NotImplementedError

    def get_info(self):
        """返回后端信息字符串"""
        return f"{self.__class__.__name__}: {self.model_path}"


class CpuBackend(InferenceBackend):
    """CPU推理后端 - 使用ultralytics YOLO (当前默认)"""

    def load(self):
        from ultralytics import YOLO
        self.model = YOLO(self.model_path)
        print(f"[CPU Backend] 模型加载完成: {self.model_path}")

    def predict(self, frame, conf=0.5):
        if self.model is None:
            self.load()
        results = self.model(frame, show=False, verbose=False, conf=conf)
        return results[0]

    def get_info(self):
        return f"CPU (ultralytics): {os.path.basename(self.model_path)}"


class OnnxBackend(InferenceBackend):
    """ONNX Runtime推理后端 - 可选GPU加速

    使用方式: 将best.onnx放在QT_last目录下
    安装: pip install onnxruntime 或 pip install onnxruntime-gpu
    """

    def load(self):
        try:
            import onnxruntime as ort
        except ImportError:
            raise ImportError("请安装 onnxruntime: pip install onnxruntime-gpu")

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self.session = ort.InferenceSession(self.model_path, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        actual = self.session.get_providers()
        print(f"[ONNX Backend] 模型加载完成: {self.model_path}, providers={actual}")

    def predict(self, frame, conf=0.5):
        """ONNX推理 — 返回原始输出

        注意: ONNX输出格式与ultralytics YOLO不同，需要后处理。
        这里返回一个简化的结果包装对象，包含boxes信息。
        实际使用时建议对接ultralytics的ONNX推理接口。
        """
        if not hasattr(self, "session"):
            self.load()

        # 使用ultralytics自带的ONNX推理(最简方案)
        from ultralytics import YOLO
        if self.model is None:
            self.model = YOLO(self.model_path)
        results = self.model(frame, show=False, verbose=False, conf=conf)
        return results[0]

    def get_info(self):
        return f"ONNX Runtime: {os.path.basename(self.model_path)}"


class NpuBackend(InferenceBackend):
    """NPU推理后端 - Fibo AI Stack (Qualcomm Hexagon DSP)

    待实现: 需要Fibo AI Stack SDK
    部署路线: .pt → ONNX → Fibo AI Stack转换 → .dlc → NPU推理引擎

    已有文件: gear.dlc (9.6MB, 已转换)

    拿到SDK后实现步骤:
    1. import fibo_ai_stack (或对应SDK模块名)
    2. load(): 加载.dlc模型文件
    3. predict(): 调用SDK推理接口，将输出转换为与YOLO results兼容的格式
    """

    def load(self):
        if not self.model_path.endswith(".dlc"):
            raise ValueError(f"NPU后端需要.dlc模型文件，当前: {self.model_path}")
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"DLC模型文件不存在: {self.model_path}")
        print(f"[NPU Backend] DLC模型文件已找到: {self.model_path}")
        print("[NPU Backend] 等待Fibo AI Stack SDK集成...")
        # TODO: 拿到SDK后在此加载DLC模型
        # self.model = fibo_ai_stack.load_model(self.model_path)

    def predict(self, frame, conf=0.5):
        raise NotImplementedError(
            "NPU推理尚未实现 — 需要Fibo AI Stack SDK。\n"
            "请联系广和通技术支持或从QQ群获取SDK。\n"
            "获取后在 gp_inference_backend.py 的 NpuBackend 类中实现 predict() 方法。\n"
            f"DLC模型文件: {self.model_path}"
        )

    def get_info(self):
        return f"NPU (Hexagon DSP): {os.path.basename(self.model_path)} [未实现]"


def create_backend(backend_type, model_path):
    """工厂函数 - 创建推理后端

    Args:
        backend_type: "cpu", "onnx", "npu"
        model_path: 模型文件路径 (.pt / .onnx / .dlc)
    Returns:
        InferenceBackend实例
    """
    backends = {
        "cpu": CpuBackend,
        "onnx": OnnxBackend,
        "npu": NpuBackend,
    }
    cls = backends.get(backend_type)
    if cls is None:
        raise ValueError(f"不支持的推理后端: {backend_type}，可选: {list(backends.keys())}")

    backend = cls(model_path)
    backend.load()
    return backend

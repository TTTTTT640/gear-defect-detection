from ultralytics import YOLO

import os
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
model = YOLO(os.path.join(_BASE_DIR, "best.pt"))

model.export(
    format="onnx",
    imgsz=(640,640),
    keras=False,
    optimize=False,
    half=False,
    int8=False,
    dynamic=False,
    simplify=True,
    opset=12,
    workspace=4.0,
    nms=False,
    batch=1,
    device="cpu"
)
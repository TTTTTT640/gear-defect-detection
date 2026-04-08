"""
YOLOv8 齿轮检测模型训练脚本
在RTX 4060 PC上运行

用法:
  python gp_train.py                          # 使用默认配置训练
  python gp_train.py --data gear_dataset.yaml  # 指定数据集
  python gp_train.py --epochs 200 --batch 16   # 自定义参数
  python gp_train.py --resume runs/detect/train/weights/last.pt  # 断点续训
"""

import os
import argparse
from datetime import datetime


# ============================================================
#  数据集目录结构说明
# ============================================================
DATASET_STRUCTURE = """
在训练之前，请按以下结构准备数据集：

gear_dataset/
├── images/
│   ├── train/          # 训练集图片 (建议 >500张)
│   │   ├── gear_001.jpg
│   │   ├── gear_002.jpg
│   │   └── ...
│   └── val/            # 验证集图片 (建议 train的20%)
│       ├── gear_101.jpg
│       └── ...
├── labels/
│   ├── train/          # 训练集标注 (YOLO格式 txt)
│   │   ├── gear_001.txt
│   │   └── ...
│   └── val/
│       ├── gear_101.txt
│       └── ...
└── gear_dataset.yaml   # 数据集配置文件

gear_dataset.yaml 内容:
---
path: ./gear_dataset    # 数据集根目录
train: images/train
val: images/val

names:
  0: good     # 齿轮完好
  1: miss     # 缺齿
  2: bad      # 表面缺陷
  3: well     # 合格(细分类)

标注工具推荐: LabelImg (YOLO格式) 或 Roboflow
"""


def create_default_yaml(output_path):
    """创建默认数据集配置文件"""
    content = """# 齿轮缺陷检测数据集配置
path: ./gear_dataset
train: images/train
val: images/val

names:
  0: good
  1: miss
  2: bad
  3: well
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"已创建数据集配置: {output_path}")


def train(args):
    """执行模型训练"""
    from ultralytics import YOLO

    # 选择基础模型
    if args.resume:
        print(f"断点续训: {args.resume}")
        model = YOLO(args.resume)
    elif args.base_model:
        print(f"基础模型: {args.base_model}")
        model = YOLO(args.base_model)
    else:
        print("使用 YOLOv8n (最小模型，适合边缘部署)")
        model = YOLO("yolov8n.pt")

    # 检查数据集配置
    if not os.path.exists(args.data):
        print(f"数据集配置文件不存在: {args.data}")
        print(DATASET_STRUCTURE)
        create_default_yaml(args.data)
        print("请填充数据集后重新运行训练")
        return

    # 训练参数 (针对3D打印齿轮优化)
    train_args = {
        "data": args.data,
        "epochs": args.epochs,
        "batch": args.batch,
        "imgsz": args.imgsz,
        "device": args.device,
        "workers": args.workers,
        "patience": 50,         # 早停patience
        "save_period": 10,      # 每10个epoch保存
        "project": args.project,
        "name": args.name or f"gear_{datetime.now().strftime('%m%d_%H%M')}",

        # 数据增强 (针对工业检测场景优化)
        "hsv_h": 0.01,         # 色调变化小(齿轮颜色单一)
        "hsv_s": 0.3,          # 饱和度变化
        "hsv_v": 0.4,          # 明度变化大(模拟不同光照)
        "degrees": 180,        # 旋转360度(齿轮方向无关)
        "translate": 0.1,      # 平移
        "scale": 0.3,          # 缩放
        "fliplr": 0.5,         # 水平翻转
        "flipud": 0.5,         # 垂直翻转
        "mosaic": 1.0,         # Mosaic增强
        "mixup": 0.1,          # MixUp增强
        "erasing": 0.1,        # 随机擦除(模拟遮挡)
    }

    print("=" * 50)
    print("开始训练")
    print(f"  设备: {args.device}")
    print(f"  数据集: {args.data}")
    print(f"  Epochs: {args.epochs}")
    print(f"  Batch: {args.batch}")
    print(f"  图像尺寸: {args.imgsz}")
    print("=" * 50)

    results = model.train(**train_args)

    # 训练完成后导出
    best_path = os.path.join(args.project, train_args["name"], "weights", "best.pt")
    if os.path.exists(best_path):
        print(f"\n训练完成! 最佳模型: {best_path}")

        if args.export_onnx:
            print("导出ONNX...")
            export_model = YOLO(best_path)
            export_model.export(
                format="onnx",
                imgsz=(args.imgsz, args.imgsz),
                simplify=True,
                opset=12,
                batch=1,
                device="cpu"
            )
            print("ONNX导出完成")

        print("\n下一步:")
        print(f"  1. 将 {best_path} 拷贝到 QT_last/ 目录")
        print("  2. 在V3上测试: python3 gp_main.py")
        print("  3. NPU部署: 使用Fibo AI Stack将ONNX转为DLC格式")


def main():
    parser = argparse.ArgumentParser(
        description="齿轮缺陷检测模型训练 (YOLOv8)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=DATASET_STRUCTURE
    )
    parser.add_argument("--data", type=str, default="gear_dataset.yaml",
                        help="数据集配置文件路径")
    parser.add_argument("--base-model", type=str, default=None,
                        help="基础模型 (默认yolov8n.pt)")
    parser.add_argument("--resume", type=str, default=None,
                        help="断点续训模型路径")
    parser.add_argument("--epochs", type=int, default=100,
                        help="训练轮数 (默认100)")
    parser.add_argument("--batch", type=int, default=16,
                        help="批大小 (RTX 4060建议16)")
    parser.add_argument("--imgsz", type=int, default=640,
                        help="输入图像尺寸 (默认640)")
    parser.add_argument("--device", type=str, default="0",
                        help="训练设备 (0=第一块GPU, cpu=CPU)")
    parser.add_argument("--workers", type=int, default=4,
                        help="数据加载线程数")
    parser.add_argument("--project", type=str, default="runs/detect",
                        help="训练结果保存目录")
    parser.add_argument("--name", type=str, default=None,
                        help="实验名称")
    parser.add_argument("--export-onnx", action="store_true",
                        help="训练完成后自动导出ONNX")

    args = parser.parse_args()
    train(args)


if __name__ == "__main__":
    main()

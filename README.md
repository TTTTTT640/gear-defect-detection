# 工业齿轮缺陷检测系统

基于广和通 SC171 V3 (Qualcomm QCM6490) 开发板 + YOLO 的工业齿轮缺陷实时检测系统。

## 系统架构

```
摄像头采集 → 自适应补光(帧亮度分析→PWM)
           → 阶段0: 齿轮存在性检测 (best.pt, conf=0.6)
                ├── "good" → 停传送带 → 阶段1: 缺陷分类 (final2.pt, conf=0.7)
                │                          ├── "well" → 合格放行 (串口01) → 写日志
                │                          └── "bad"  → 缺陷剔除 (串口02) → 写日志 → SMS检查
                └── "miss" → 缺齿剔除 (串口02) → 写日志 → SMS检查
```

## 功能列表

| 功能 | 状态 | 模块 |
|------|------|------|
| 两阶段YOLO检测 (存在性→缺陷分类) | 已实现 | `gp_detectionworker.py` |
| 双摄像头采集 (QThread) | 已实现 | `gp_cameradisplaywidget.py` |
| 串口通信控制传送带/分拣 | 已实现 | `gp_serial.py` |
| PyQt5 GUI界面 | 已实现 | `gp_mainwindow.py` |
| 检测日志 + Excel导出 | 已实现 | `gp_logger.py` |
| SMS短信报警 (连续缺陷超阈值) | 已实现 | `gp_sms.py` |
| 自适应补光 (帧亮度→PWM) | 已实现 | `gp_lighting.py` |
| 推理后端抽象 (CPU/ONNX/NPU) | 已实现 | `gp_inference_backend.py` |
| 实时统计图表 (饼图+柱状图) | 已实现 | `gp_chartwidget.py` |
| 检测历史记录表 | 已实现 | `gp_chartwidget.py` |
| 模型切换 (UI下拉框) | 已实现 | `gp_detectiondisplaywidget.py` |
| 菜单栏 (导出/SMS配置/补光参数) | 已实现 | `gp_mainwindow.py` |
| PC模拟测试版 (Windows兼容) | 已实现 | `pc_test.py` |
| V3一键部署脚本 | 已实现 | `deploy_v3.sh` |
| 模型训练脚本 (RTX 4060) | 已实现 | `gp_train.py` |
| NPU加速推理 (Fibo AI Stack) | 占位，需SDK | `gp_inference_backend.py` |

## 硬件平台

| 组件 | 规格 |
|------|------|
| 开发板 | 广和通 SC171 V3 (EVB-SOC-U) |
| 芯片 | Qualcomm QCM6490 |
| CPU | Kryo 670 八核 (2.7GHz + 2.2GHz + 1.7GHz) |
| NPU | Hexagon DSP + HTA, 13 TOPS |
| RAM | 8GB LPDDR4X |
| 存储 | 128GB UMCP |
| 摄像头 | USB摄像头 x2 (V4L2) |
| 串口 | /dev/ttyHS1 @ 9600 baud |
| 齿轮样品 | 3D打印 |

## 文件结构

```
QT_last/
├── gp_main.py                    # 程序入口
├── gp_mainwindow.py              # 主窗口 (菜单栏+图表+历史表)
├── gp_cameradisplaywidget.py     # 摄像头采集 (QThread)
├── gp_detectiondisplaywidget.py  # 检测结果 + 状态机 + 模型切换
├── gp_detectionworker.py         # YOLO检测工作线程 + 亮度分析
├── gp_globals.py                 # 全局状态 + 推理后端 + 模块实例
├── gp_serial.py                  # 串口通信 (含PWM发送/数据读取)
├── gp_logger.py                  # 检测日志 + Excel导出
├── gp_sms.py                     # SMS短信报警 (AT指令/Mock)
├── gp_lighting.py                # 自适应补光 (亮度分析+PWM)
├── gp_inference_backend.py       # 推理后端抽象 (CPU/ONNX/NPU)
├── gp_chartwidget.py             # 统计图表 + 检测历史表
├── gp_train.py                   # 模型训练脚本 (YOLOv8)
├── pc_test.py                    # PC模拟测试版 (Windows兼容)
├── deploy_v3.sh                  # V3一键部署脚本
├── zhuanhua.py                   # 模型ONNX导出工具
├── requirements.txt              # Python依赖
├── V3_CODE_REVIEW.md             # V3数据手册代码审查报告
├── PROJECT_ANALYSIS.md           # 项目分析与改进方案
├── best.pt                       # 齿轮存在性检测模型 (git忽略)
├── final2.pt                     # 缺陷分类模型 (git忽略)
├── best.onnx                     # ONNX格式模型 (git忽略)
└── gear.dlc                      # Qualcomm DLC格式 (git忽略)
```

## 快速开始

### PC模拟测试 (Windows/Linux)

```bash
cd QT_last
pip install -r requirements.txt
pip install ultralytics

# 摄像头测试
python pc_test.py --camera 0

# 图片测试
python pc_test.py --image path/to/gear.jpg

# 视频测试
python pc_test.py --video path/to/gear.mp4
```

PC版特性：模拟串口(仅打印)、实时FPS/推理时间显示、截图保存、串口日志查看。

### V3开发板部署

```bash
cd QT_last
bash deploy_v3.sh
```

部署脚本自动完成：依赖安装、模型检查、串口权限配置、启动程序。

### 模型训练 (RTX 4060)

```bash
cd QT_last

# 使用默认配置
python gp_train.py --data gear_dataset.yaml

# 自定义参数
python gp_train.py --epochs 200 --batch 16 --export-onnx

# 断点续训
python gp_train.py --resume runs/detect/train/weights/last.pt
```

运行 `python gp_train.py --help` 查看数据集结构说明和全部参数。

## 串口协议

| 指令 | 方向 | 含义 |
|------|------|------|
| `07` | V3→下位机 | 启动传送带 |
| `08` | V3→下位机 | 停止传送带 |
| `01` | V3→下位机 | 合格放行 |
| `02` | V3→下位机 | 缺陷剔除 |
| `PWM:XXX` | V3→下位机 | 补光灯占空比 (000~100) |

## 推理后端

系统支持三种推理后端，在 `gp_globals.py` 中通过 `BACKEND_TYPE` 切换：

| 后端 | 配置值 | 模型格式 | 状态 |
|------|--------|----------|------|
| CPU (ultralytics) | `"cpu"` | `.pt` | 默认，可用 |
| ONNX Runtime | `"onnx"` | `.onnx` | 可用，需装onnxruntime |
| NPU (Hexagon DSP) | `"npu"` | `.dlc` | 占位，需Fibo AI Stack SDK |

## 模型文件

模型文件未包含在git仓库中（.gitignore），需手动拷贝到 `QT_last/` 目录：

| 文件 | 用途 | 获取方式 |
|------|------|----------|
| `best.pt` | 阶段0 齿轮存在性检测 | `gp_train.py` 训练 |
| `final2.pt` | 阶段1 缺陷分类 | `gp_train.py` 训练 |
| `best.onnx` | ONNX推理后端 | `zhuanhua.py` 导出 |
| `gear.dlc` | NPU推理 | Fibo AI Stack 转换 |

## 待完成

- [ ] 获取 Fibo AI Stack SDK，实现 `NpuBackend.predict()` 完成NPU加速
- [ ] 准备齿轮图片/视频数据集，在4060上训练优化模型
- [ ] V3实机全链路联调 (传送带+分拣+检测+补光+报警)

## 竞赛

2026全国大学生嵌入式芯片与系统设计竞赛 — 泛边缘智能终端命题

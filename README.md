# 工业齿轮缺陷检测系统

基于广和通 SC171 V3 (Qualcomm QCM6490) 开发板 + YOLO 的工业齿轮缺陷实时检测系统。

## 系统架构

```
摄像头采集 → 阶段0: 齿轮存在性检测 (best.pt, conf=0.6)
                ├── "good" → 停传送带 → 阶段1: 缺陷分类 (final2.pt, conf=0.7)
                │                          ├── "well" → 合格放行 (串口01)
                │                          └── "bad"  → 缺陷剔除 (串口02)
                └── "miss" → 缺齿剔除 (串口02)
```

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
├── gp_main.py                  # 程序入口
├── gp_mainwindow.py            # 主窗口布局
├── gp_cameradisplaywidget.py   # 摄像头采集 (QThread)
├── gp_detectiondisplaywidget.py # 检测结果展示 + 状态机
├── gp_detectionworker.py       # YOLO检测工作线程
├── gp_globals.py               # 全局状态 + 模型加载
├── gp_serial.py                # 串口通信管理
├── pc_test.py                  # PC模拟测试版 (Windows兼容)
├── deploy_v3.sh                # V3一键部署脚本
├── zhuanhua.py                 # 模型ONNX导出工具
├── requirements.txt            # Python依赖
├── V3_CODE_REVIEW.md           # V3数据手册代码审查报告
├── PROJECT_ANALYSIS.md         # 项目分析与改进方案
├── best.pt                     # 齿轮存在性检测模型 (5.1MB, git忽略)
├── final2.pt                   # 缺陷分类模型 (5.2MB, git忽略)
└── gear.dlc                    # Qualcomm DLC格式 (9.6MB, 待对接NPU)
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

## 串口协议

| 指令 | 方向 | 含义 |
|------|------|------|
| `07` | V3→下位机 | 启动传送带 |
| `08` | V3→下位机 | 停止传送带 |
| `01` | V3→下位机 | 合格放行 |
| `02` | V3→下位机 | 缺陷剔除 |

## 模型文件

模型文件未包含在git仓库中（.gitignore），需手动拷贝到 `QT_last/` 目录：

| 文件 | 用途 | 获取方式 |
|------|------|----------|
| `best.pt` | 阶段0 齿轮存在性检测 | 自行训练 |
| `final2.pt` | 阶段1 缺陷分类 | 自行训练 |
| `gear.dlc` | NPU推理模型 | Fibo AI Stack 转换 |

## 待实现

- [ ] NPU加速推理 (DLC部署，需Fibo AI Stack SDK)
- [ ] 检测日志记录 + Excel导出
- [ ] SMS短信报警 (缺陷过多时)
- [ ] 自适应补光 (ADC+PWM)
- [ ] UI界面美化 + 统计图表

## 竞赛

2026全国大学生嵌入式芯片与系统设计竞赛 — 泛边缘智能终端命题

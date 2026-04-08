# SC171 V3 工业齿轮检测系统 - 代码审查与改进报告

> 基于广和通 SC171 V3 (QCM6490) 2026版数据手册进行代码审查
> 审查日期: 2026-04-08

---

## 一、项目概览

### 1.1 系统功能
基于 PyQt5 + YOLO 的工业齿轮缺陷实时检测系统，部署于广和通 SC171 V3 开发板。

**两阶段检测流程:**
```
摄像头采集 → 阶段0(gear存在性检测, model1, conf=0.6)
           → 检测到齿轮("good") → 停传送带 → 阶段1(缺陷分类, model2, conf=0.7)
              → "well": 合格放行(01) → 回到阶段0
              → "bad":  缺陷剔除(02) → 回到阶段0
           → 检测到缺齿("miss") → 直接剔除(02) → 回到阶段0
```

### 1.2 文件结构
| 文件 | 功能 | 行数 |
|------|------|------|
| `gp_main.py` | 程序入口，Qt应用初始化 | 28 |
| `gp_mainwindow.py` | 主窗口布局，管理摄像头和检测面板 | ~115 |
| `gp_cameradisplaywidget.py` | QThread摄像头采集与显示 | ~120 |
| `gp_detectiondisplaywidget.py` | 检测结果展示 + 串口指令派发(状态机) | ~290 |
| `gp_detectionworker.py` | YOLO检测工作线程 | ~99 |
| `gp_globals.py` | 全局状态变量和模型加载 | ~28 |
| `gp_serial.py` | 串口通信管理 (ttyHS1, 9600baud) | ~66 |
| `zhuanhua.py` | 模型ONNX导出脚本 | ~17 |

### 1.3 模型文件
| 文件 | 大小 | 用途 |
|------|------|------|
| `best.pt` | 5.1MB | YOLOv8 齿轮检测基础模型 |
| `best.onnx` | 9.8MB | ONNX导出版本 |
| `final2.pt` | 5.2MB | 缺陷分类模型 (阶段2) |
| `Fina_ll.pt` | 5.2MB | 备用模型 |
| `newb.pt` | 5.2MB | 备用模型 |
| `gear.dlc` | 9.6MB | **Qualcomm DLC格式** (已转换，未使用) |

---

## 二、已修复的代码问题

### 2.1 Bug修复

#### [FIX-1] gp_main.py - CSS拼写错误
```diff
- bakground-color: #f5f6fa;
+ background-color: #f5f6fa;
```
**影响:** 主窗口背景色样式无法生效。

#### [FIX-2] gp_globals.py - 硬编码绝对路径
```diff
- model = YOLO("/home/fibo/Desktop/ultralytics-8.4.13/gear.pt")
- model2= YOLO("/home/fibo/Desktop/QT/final2.pt")
+ _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
+ MODEL1_PATH = os.path.join(_BASE_DIR, "best.pt")
+ MODEL2_PATH = os.path.join(_BASE_DIR, "final2.pt")
+ model = YOLO(MODEL1_PATH)
+ model2 = YOLO(MODEL2_PATH)
```
**影响:** 原路径在不同部署环境下必然报错，现在使用脚本所在目录的相对路径。

#### [FIX-3] zhuanhua.py - 同样的硬编码路径问题
```diff
- model = YOLO("/home/fibo/Desktop/QT/best.pt")
+ _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
+ model = YOLO(os.path.join(_BASE_DIR, "best.pt"))
```

#### [FIX-4] gp_cameradisplaywidget.py - 不可达代码
```diff
  except Exception as e:
      print(f"摄像头启动错误: {e}")
      self.setText(f"错误: {str(e)}")
      return False
- return True  # 永远不会执行到这里
```

#### [FIX-5] gp_mainwindow.py - closeEvent中阻塞主线程
```diff
  self.detection_display.stop_detection_thread()
- time.sleep(0.5)  # 阻塞UI线程
+ # 等待线程结束（QThread.wait已在stop_camera中处理）
  event.accept()
```
**影响:** `time.sleep(0.5)` 在GUI线程中阻塞会导致窗口关闭时卡顿。`stop_camera()` 内部已调用 `QThread.wait()` 等待线程结束，无需额外sleep。

### 2.2 代码质量改进

#### [IMPROVE-1] 状态机变量重命名 (gp_globals.py)
| 原名 | 新名 | 含义 |
|------|------|------|
| `flag` | `conveyor_running` | 传送带状态: 0=停止, 1=运行 |
| `rest2` | `defect_confirmed` | 缺陷确认标记 |
| `rest3` | `pass_debounce` | 合格品防抖标记 |
| `goodsignal` | `detection_stage` | 检测阶段: 0=存在性, 1=缺陷分类 |

#### [IMPROVE-2] 消除重复代码 (gp_detectionworker.py)
原代码中 `goodsignal==0` 和 `goodsignal==1` 两个分支几乎完全相同（约60行重复代码），提取为公共方法 `_run_model_and_emit()`。

#### [IMPROVE-3] 模块级全局变量 → 实例变量 (gp_detectiondisplaywidget.py)
```diff
- rest = 0      # 模块级全局变量，多实例时会冲突
- interrupt = 0  # 未使用的变量
+ self.send_debounce = 0  # 实例变量
```

#### [IMPROVE-4] 清理未使用的导入
- `gp_mainwindow.py`: 移除未使用的 `time`, `QTimer`, `QThread`
- `gp_cameradisplaywidget.py`: 移除未使用的 `threading`

#### [IMPROVE-5] 状态机逻辑注释 (gp_detectiondisplaywidget.py)
为 `update_detection_display` 方法添加了完整的状态转换注释文档。

---

## 三、V3硬件规格与代码对照

### 3.1 核心硬件参数 (V3 2026版)
| 参数 | 规格 | 代码现状 |
|------|------|----------|
| CPU | Kryo 670, 8核 (1x2.7G + 3x2.2G + 4x1.7G) | 当前使用CPU做YOLO推理 |
| GPU | Adreno 642 | 仅用于图形渲染，不适合AI推理 |
| NPU | Hexagon DSP + HTA, **13 TOPS** | **未使用** (gear.dlc已存在) |
| RAM | 8GB LPDDR4X | 足够 |
| 存储 | 128GB UMCP | 足够 |
| 摄像头 | MIPI CSI, USB | 代码使用USB摄像头 (V4L2) |
| 串口 | 7x UART, RS232, RS485 | 使用 /dev/ttyHS1 @ 9600 |
| GPIO | 8通道 | 可用于分拣机构控制 |
| PWM | 1通道 (与LED复用) | 可用于补光灯控制 |
| LAN | 百兆以太网 x2 | 可用于远程监控 |
| CAN | 2通道 | 可用于工业传送带通信 |
| ADC | 2通道 | 可用于光照传感器 |

### 3.2 V3接口与代码匹配分析

#### 串口通信 - 匹配
```python
# gp_serial.py - 使用 ttyHS1 对应V3的UART接口
SerialManager(port='/dev/ttyHS1', baudrate=9600)
```
V3提供7路UART，ttyHS1是其中一路高速串口，配置正确。

#### 摄像头采集 - 匹配
```python
# gp_cameradisplaywidget.py - 使用V4L2采集
cap = cv2.VideoCapture(self.camera_id, cv2.CAP_V4L2)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
```
V3支持USB摄像头，V4L2驱动在Linux上正确。320x240分辨率偏低但有利于检测速度。

#### NPU推理 - **未对接** (关键改进点)
```python
# 当前: CPU推理（慢）
model = YOLO(MODEL1_PATH)  # ultralytics CPU推理

# 目标: NPU推理（快10-50x）
# gear.dlc 已存在，需要 Fibo AI Stack SDK 进行对接
# 部署路线: .pt → ONNX → Fibo AI Stack → .dlc → NPU推理引擎
```

### 3.3 V3 Fibo AI Stack 部署路线
根据V3 2026版数据手册:
```
训练框架 (PyTorch/TensorFlow)
    ↓
模型压缩/转换 (PC/虚拟机上完成)
    ↓
DLC格式模型文件
    ↓
端侧推理引擎 (SC171 V3 NPU)
    ↓
应用层 (CV/Audio/LLM)
```

**已适配模型库**: YOLOv5, YOLOv8-Det, YOLOv10n-Det, YOLOv11s-best, YOLO-NAS 等。

---

## 四、串口通信协议

| 指令 | 含义 | 触发条件 |
|------|------|----------|
| `"07"` | 启动传送带 | 检测开始 / 防抖超时恢复 |
| `"08"` | 停止传送带 | 检测到目标 / 检测结束 |
| `"01"` | 合格放行 | 阶段1检测到"well" |
| `"02"` | 缺陷剔除 | 检测到"miss"或"bad" |

---

## 五、当前系统状态

### 5.1 已完成
- [x] 双摄像头采集 (QThread)
- [x] 两阶段YOLO检测 (存在性 → 缺陷分类)
- [x] 串口通信控制传送带/分拣
- [x] PyQt5 GUI界面
- [x] 检测频率可调 (0.1s/0.3s/0.5s)
- [x] gear.dlc 模型文件已转换
- [x] best.onnx 中间格式已导出

### 5.2 硬件已就绪
- [x] V3开发板
- [x] 传送带和分拣机构
- [x] 3D打印齿轮样品
- [x] PC端 NVIDIA RTX 4060 (模型训练)

### 5.3 待实现功能
| 优先级 | 功能 | 依赖 |
|--------|------|------|
| P0 | NPU加速推理 (DLC部署) | 需获取 Fibo AI Stack SDK |
| P1 | 检测日志记录 + Excel导出 | 无依赖，可立即开发 |
| P1 | UI界面美化 | 无依赖，可立即开发 |
| P2 | SMS短信报警 (缺陷过多) | V3 4G模块，AT指令 |
| P2 | 自适应补光 (ADC+PWM) | V3 ADC采集 + PWM输出 |
| P3 | 多模型管理界面 | 无依赖 |
| P3 | PC模拟调试版本 | 无依赖，可立即开发 |

---

## 六、下一步开发计划

### 阶段1: 基础完善 (可立即开始)
1. **检测日志系统** - 记录每次检测结果，支持Excel导出
2. **UI界面升级** - 添加统计图表、检测历史、模型切换面板
3. **PC模拟版** - 用视频文件替代摄像头，方便在4060 PC上调试

### 阶段2: 硬件对接 (需SDK/硬件)
4. **NPU加速** - 获取Fibo AI Stack SDK后，对接gear.dlc进行NPU推理
5. **自适应补光** - 利用V3的ADC读取光照传感器，PWM控制补光灯亮度
6. **SMS报警** - 利用V3 4G模块发送AT指令实现短信通知

### 阶段3: 优化竞赛
7. **模型优化** - 在RTX 4060上训练更优模型，针对3D打印齿轮优化数据集
8. **整体联调** - 传送带 + 分拣 + 检测 + 报警全链路测试

---

## 七、关键注意事项

1. **gear.dlc 已存在但未使用** - 这是最大的性能提升点，一旦拿到SDK应优先对接
2. **CPU推理瓶颈** - 当前ARM CPU跑YOLO很慢，NPU可提升10-50倍
3. **3D打印齿轮** - 模型训练数据集需匹配3D打印材质和纹理特征
4. **两个版本并行** - PC版(4060调试) + V3版(实机部署)，注意代码兼容性
5. **串口协议简单** - 当前仅4条指令，后续扩展需注意协议版本管理

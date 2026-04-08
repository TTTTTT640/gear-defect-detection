# QT_last 工业齿轮检测系统 - 完整工程分析与改进方案

---

## 第一部分：工程内容解析

### 1.1 项目概述

这是一个运行在嵌入式Linux平台（广和通SC171 V3，基于高通QCM6490）上的**工业齿轮缺陷实时检测系统**。使用双USB摄像头采集图像，通过YOLO模型进行端侧AI推理，检测结果通过串口控制传送带执行分拣动作。

### 1.2 文件结构

```
QT_last/
├── 核心代码（gp_前缀，模块化架构）
│   ├── gp_main.py                  # 程序入口
│   ├── gp_mainwindow.py            # 主窗口（布局：双摄像头+检测面板）
│   ├── gp_cameradisplaywidget.py   # 摄像头采集控件（QThread）
│   ├── gp_detectiondisplaywidget.py# 检测结果显示+串口指令分发+状态机逻辑
│   ├── gp_detectionworker.py       # YOLO检测工作线程（双模型切换）
│   ├── gp_globals.py              # 全局变量（模型实例、帧缓冲、状态标志）
│   └── gp_serial.py              # 串口通信管理（/dev/ttyHS1, 9600baud）
│
├── 模型文件
│   ├── best.pt / best.onnx        # YOLO模型（齿轮检测）
│   ├── final2.pt / Fina_ll.pt     # YOLO模型（缺陷分类：bad/well/miss）
│   ├── newb.pt                     # 模型变体
│   └── gear.dlc                    # 高通DLC格式模型（已转换，9.6MB）
│
├── 原型/测试文件
│   ├── new1                        # 原始单文件原型（重构前）
│   ├── aicodenmnmnm.py            # 双摄像头测试
│   ├── double_cam.py              # 双摄像头测试
│   ├── finaltest.py               # OpenCV+YOLO独立测试
│   ├── seria1l.py                 # 串口独立测试
│   ├── zhuanhua.py                # 模型导出脚本（PT→ONNX）
│   ├── shuangmian_test.py         # 空文件
│   └── cam_dis_copy.txt           # 代码备份
│
├── ultralytics/                    # 完整的Ultralytics YOLO库（含v3~v26模型定义）
├── .pylintrc                       # Pylint配置
└── readme.txt                      # 开发笔记
```

### 1.3 系统架构图

```
┌──────────────────────────────────────────────────────────────┐
│                     gp_main.py (入口)                        │
│                          │                                    │
│                   gp_mainwindow.py                            │
│              ┌───────────┼───────────┐                        │
│              ▼           ▼           ▼                        │
│     CameraDisplay  CameraDisplay  DetectionDisplay            │
│     Widget(cam4)   Widget(cam2)   Widget                      │
│         │              │              │                        │
│    QThread采集     QThread采集    toggle_detection()           │
│         │              │              │                        │
│         └──────┬───────┘     DetectionWorker                  │
│                ▼             (threading.Thread)                │
│         gp_globals.frame          │                           │
│                │         ┌────────┴────────┐                  │
│                └────────►│ goodsignal==0?  │                  │
│                          │  YES: model1    │                  │
│                          │  NO:  model2    │                  │
│                          └────────┬────────┘                  │
│                                   ▼                           │
│                          检测结果分发                          │
│                     ┌─────┼─────┼─────┐                      │
│                     ▼     ▼     ▼     ▼                      │
│                   "01"  "02"  "07"  "08"                     │
│                     └─────┼─────┼─────┘                      │
│                           ▼                                   │
│                    gp_serial.py                               │
│               (/dev/ttyHS1, 9600)                            │
│                           │                                   │
│                    传送带/分拣机构                             │
└──────────────────────────────────────────────────────────────┘
```

### 1.4 状态机（当前逻辑）

当前系统使用 `goodsignal` 作为核心状态变量，实现两阶段检测：

```
状态0 (goodsignal=0): 使用 model1(gear.pt) 检测齿轮是否存在
    ├── 检测到 "good" → goodsignal=1, 发送"08"停带, 进入状态1
    ├── 检测到 "miss" → 发送"02"报警+"08"停带, 保持状态0
    └── 未检测到 → 继续扫描

状态1 (goodsignal=1): 使用 model2(final2.pt) 检测缺陷类型
    ├── 检测到 "well" → 发送"01"合格, goodsignal=0, 2.3s防抖
    ├── 检测到 "bad"  → 发送"02"报警+"08"停带, goodsignal=0
    └── 未检测到 → 继续扫描
```

**当前问题**：
- `rest`, `rest2`, `rest3`, `flag`, `goodsignal` 变量命名含义不清
- 状态转换逻辑分散在 `gp_detectiondisplaywidget.py` 和 `gp_detectionworker.py` 两个文件中
- 防抖逻辑用全局变量+QTimer实现，容易出竞态条件
- 没有明确的状态枚举定义

### 1.5 串口通信协议

| 指令 | 含义 | 触发条件 |
|------|------|---------|
| `"01"` | 合格品通过 | 状态1检测到"well" |
| `"02"` | 不合格/报警 | 检测到"miss"或"bad" |
| `"07"` | 启动传送带 | 检测完成/防抖结束 |
| `"08"` | 停止传送带 | 检测到目标需要判断时 |

---

## 第二部分：代码功能修改方案

### 2.1 缺陷过多报警 → 发送短信

#### 方案：使用4G模组AT指令发送短信

SC171 V3本身不带5G/4G模组（V3砍了），但可通过以下方式实现：

**方案A：外接L610 CAT1模组发短信（推荐，和竞赛4G IoT方向结合）**

```python
# sms_alert.py - 短信报警模块
import serial
import time

class SMSAlert:
    """通过L610 CAT1模组发送短信报警"""
    
    def __init__(self, port='/dev/ttyUSB0', baudrate=115200):
        self.ser = serial.Serial(port, baudrate, timeout=2)
        self.defect_count = 0
        self.defect_threshold = 10      # 连续10个缺陷触发报警
        self.alert_cooldown = 300       # 报警冷却时间（秒）
        self.last_alert_time = 0
        self.phone_number = "+8613800138000"  # 接收报警的手机号
    
    def record_defect(self, defect_type):
        """记录缺陷，判断是否需要报警"""
        self.defect_count += 1
        if self.defect_count >= self.defect_threshold:
            current_time = time.time()
            if current_time - self.last_alert_time > self.alert_cooldown:
                self.send_sms(f"[齿轮检测报警] 连续检测到{self.defect_count}个缺陷品，"
                            f"最新缺陷类型: {defect_type}，请立即检查产线！")
                self.last_alert_time = current_time
                self.defect_count = 0
    
    def record_good(self):
        """记录合格品，重置缺陷计数"""
        self.defect_count = 0
    
    def send_sms(self, message):
        """通过AT指令发送短信"""
        try:
            self._send_at("AT+CMGF=1")          # 设置文本模式
            time.sleep(0.5)
            self._send_at(f'AT+CMGS="{self.phone_number}"')
            time.sleep(0.5)
            self.ser.write(message.encode('utf-8'))
            self.ser.write(b'\x1a')              # Ctrl+Z 发送
            time.sleep(3)
            response = self.ser.read(200).decode('utf-8', errors='ignore')
            print(f"短信发送结果: {response}")
            return 'OK' in response
        except Exception as e:
            print(f"短信发送失败: {e}")
            return False
    
    def _send_at(self, cmd):
        self.ser.write((cmd + '\r\n').encode())
        time.sleep(0.3)
        return self.ser.read(200).decode('utf-8', errors='ignore')
```

**方案B：通过WiFi调用云短信API（更简单）**

```python
# 使用阿里云/腾讯云短信SDK（V3有WiFi）
import requests

def send_sms_via_cloud(phone, message):
    """通过云服务API发短信（需预先配置）"""
    # 以阿里云短信为例
    url = "https://dysmsapi.aliyuncs.com"
    params = {
        "PhoneNumbers": phone,
        "SignName": "齿轮检测",
        "TemplateCode": "SMS_XXXXX",
        "TemplateParam": f'{{"defect_count":"{message}"}}'
    }
    # ... 签名认证逻辑
    requests.get(url, params=params)
```

**集成位置**：在 `gp_detectiondisplaywidget.py` 的 `update_detection_display()` 中，每次检测到 "bad" 或 "miss" 时调用 `sms_alert.record_defect()`。

---

### 2.2 检测日志 + Excel导出

```python
# gp_logger.py - 检测日志模块
import csv
import os
import time
from datetime import datetime
from collections import defaultdict

class DetectionLogger:
    """检测日志记录器，支持Excel(CSV)导出"""
    
    def __init__(self, log_dir="./logs"):
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)
        
        # 当前会话统计
        self.session_start = datetime.now()
        self.total_count = 0
        self.good_count = 0
        self.bad_count = 0
        self.miss_count = 0
        self.records = []  # 详细记录列表
        
        # 创建日志文件
        timestamp = self.session_start.strftime("%Y%m%d_%H%M%S")
        self.csv_path = os.path.join(log_dir, f"detection_{timestamp}.csv")
        self.summary_path = os.path.join(log_dir, f"summary_{timestamp}.txt")
        
        # 写CSV头
        with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "序号", "时间", "检测结果", "置信度", 
                "模型", "累计合格", "累计不合格", "当前良率(%)"
            ])
    
    def log(self, class_name, confidence, model_name):
        """记录一次检测结果"""
        self.total_count += 1
        
        if class_name in ("good", "well"):
            self.good_count += 1
            result = "合格"
        elif class_name == "bad":
            self.bad_count += 1
            result = "不合格-缺陷"
        elif class_name == "miss":
            self.miss_count += 1
            result = "不合格-缺齿"
        else:
            result = class_name
        
        yield_rate = (self.good_count / self.total_count * 100) if self.total_count > 0 else 0
        
        record = {
            "id": self.total_count,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "result": result,
            "confidence": f"{confidence:.4f}",
            "model": model_name,
            "good_total": self.good_count,
            "bad_total": self.bad_count + self.miss_count,
            "yield_rate": f"{yield_rate:.1f}"
        }
        self.records.append(record)
        
        # 实时写入CSV（追加模式）
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                record["id"], record["time"], record["result"],
                record["confidence"], record["model"],
                record["good_total"], record["bad_total"], record["yield_rate"]
            ])
        
        return record
    
    def generate_summary(self):
        """生成检测总结报告"""
        duration = datetime.now() - self.session_start
        hours, remainder = divmod(int(duration.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        yield_rate = (self.good_count / self.total_count * 100) if self.total_count > 0 else 0
        
        summary = f"""
========================================
      工业齿轮检测报告
========================================
检测时间：{self.session_start.strftime("%Y-%m-%d %H:%M:%S")} ~ {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
检测时长：{hours}小时{minutes}分{seconds}秒

总检测数：{self.total_count}
  合格品：{self.good_count}
  缺陷品：{self.bad_count}
  缺齿品：{self.miss_count}

良    率：{yield_rate:.1f}%

详细CSV：{self.csv_path}
========================================
"""
        with open(self.summary_path, 'w', encoding='utf-8') as f:
            f.write(summary)
        
        return summary

    def get_stats(self):
        """获取当前统计数据（供UI显示）"""
        yield_rate = (self.good_count / self.total_count * 100) if self.total_count > 0 else 0
        return {
            "total": self.total_count,
            "good": self.good_count,
            "bad": self.bad_count,
            "miss": self.miss_count,
            "yield_rate": yield_rate
        }
```

**集成方式**：在 `gp_globals.py` 中创建全局实例 `logger = DetectionLogger()`，在 `gp_detectionworker.py` 每次推理后调用 `logger.log()`，窗口关闭时调用 `logger.generate_summary()`。

---

### 2.3 状态机重构

当前问题：`rest`, `rest2`, `rest3`, `flag`, `goodsignal` 含义模糊，状态转换逻辑分散。

```python
# gp_statemachine.py - 清晰的状态机
from enum import Enum, auto
import time
import threading

class DetectionState(Enum):
    """检测状态枚举"""
    IDLE = auto()               # 空闲，等待齿轮进入
    DETECTING_PRESENCE = auto()  # 阶段1：检测齿轮是否存在
    DETECTING_DEFECT = auto()    # 阶段2：检测缺陷类型
    DEBOUNCE = auto()           # 防抖等待
    CONVEYOR_RUNNING = auto()    # 传送带运行中

class ModelSelector(Enum):
    """模型选择"""
    PRESENCE_MODEL = "gear.pt"      # 齿轮存在性检测模型
    DEFECT_MODEL = "final2.pt"      # 缺陷分类模型

class GearDetectionStateMachine:
    """齿轮检测状态机"""
    
    def __init__(self, serial_manager, models: dict):
        self.state = DetectionState.IDLE
        self.serial = serial_manager
        self.models = models  # {"presence": model1, "defect": model2}
        self.lock = threading.Lock()
        
        # 模型执行顺序（可配置）
        self.model_pipeline = [
            {"name": "presence", "model_key": "presence", "conf": 0.6},
            {"name": "defect",   "model_key": "defect",   "conf": 0.7},
        ]
        self.current_pipeline_stage = 0
        
        # 防抖
        self.debounce_time = 2.3  # 秒
        self.last_action_time = 0
        
        # 传送带状态
        self.conveyor_running = False
    
    def get_current_model_config(self):
        """获取当前应该使用的模型和配置"""
        with self.lock:
            if self.state == DetectionState.DETECTING_PRESENCE:
                return self.model_pipeline[0]
            elif self.state == DetectionState.DETECTING_DEFECT:
                return self.model_pipeline[1]
            return None
    
    def transition(self, event: str, **kwargs):
        """状态转换"""
        with self.lock:
            old_state = self.state
            
            if self.state == DetectionState.IDLE:
                self._start_conveyor()
                self.state = DetectionState.DETECTING_PRESENCE
                
            elif self.state == DetectionState.DETECTING_PRESENCE:
                if event == "good_detected":
                    self._stop_conveyor()
                    self.state = DetectionState.DETECTING_DEFECT
                elif event == "miss_detected":
                    self._stop_conveyor()
                    self._alert_defect()
                    self.state = DetectionState.DEBOUNCE
                    self.last_action_time = time.time()
                    
            elif self.state == DetectionState.DETECTING_DEFECT:
                if event == "well_detected":
                    self._pass_good()
                    self.state = DetectionState.DEBOUNCE
                    self.last_action_time = time.time()
                elif event == "bad_detected":
                    self._alert_defect()
                    self._stop_conveyor()
                    self.state = DetectionState.DEBOUNCE
                    self.last_action_time = time.time()
                    
            elif self.state == DetectionState.DEBOUNCE:
                if time.time() - self.last_action_time > self.debounce_time:
                    self._start_conveyor()
                    self.state = DetectionState.DETECTING_PRESENCE
            
            if old_state != self.state:
                print(f"状态转换: {old_state.name} → {self.state.name} (事件: {event})")
    
    def set_model_order(self, order: list):
        """设置模型执行顺序（可通过UI控制）
        例如: [{"name": "defect", "model_key": "defect", "conf": 0.7},
               {"name": "presence", "model_key": "presence", "conf": 0.6}]
        """
        self.model_pipeline = order
    
    # --- 执行动作 ---
    def _start_conveyor(self):
        self.serial.send("07")
        self.conveyor_running = True
    
    def _stop_conveyor(self):
        self.serial.send("08")
        self.conveyor_running = False
    
    def _pass_good(self):
        self.serial.send("01")
    
    def _alert_defect(self):
        self.serial.send("02")
```

**多模型控制**：通过 `model_pipeline` 列表定义模型执行顺序，UI中可以拖拽调整。

---

### 2.4 自动补光系统

```python
# gp_lighting.py - 自适应补光控制
import cv2
import numpy as np

class AdaptiveLighting:
    """基于图像亮度反馈的自适应补光控制"""
    
    def __init__(self, serial_manager, pwm_pin="GPIO_XX"):
        self.serial = serial_manager
        self.target_brightness = 128    # 目标亮度（0-255）
        self.tolerance = 20             # 容差范围
        self.current_pwm = 128          # 当前PWM值（0-255）
        self.min_pwm = 30
        self.max_pwm = 255
        self.kp = 0.5                   # PID比例系数
        self.ki = 0.1                   # PID积分系数
        self.integral_error = 0
        
    def analyze_brightness(self, frame):
        """分析当前帧的平均亮度"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # ROI区域（检测区域中心）
        h, w = gray.shape
        roi = gray[h//4:3*h//4, w//4:3*w//4]
        avg_brightness = np.mean(roi)
        return avg_brightness
    
    def adjust(self, frame):
        """根据当前帧亮度调整补光PWM值"""
        brightness = self.analyze_brightness(frame)
        error = self.target_brightness - brightness
        
        if abs(error) < self.tolerance:
            return self.current_pwm  # 在容差范围内不调整
        
        # PI控制器
        self.integral_error += error
        self.integral_error = max(-500, min(500, self.integral_error))  # 防积分饱和
        
        adjustment = self.kp * error + self.ki * self.integral_error
        self.current_pwm = int(max(self.min_pwm, min(self.max_pwm, self.current_pwm + adjustment)))
        
        # 通过串口发送PWM值给下位机，或直接控制V3的PWM引脚
        self._set_pwm(self.current_pwm)
        
        return self.current_pwm
    
    def _set_pwm(self, value):
        """设置PWM输出（通过V3的PWM引脚）"""
        # 方式1：直接控制Linux PWM sysfs
        try:
            with open("/sys/class/pwm/pwmchip0/pwm0/duty_cycle", 'w') as f:
                # 假设周期1000000ns(1kHz)，duty_cycle = value/255 * period
                duty = int(value / 255 * 1000000)
                f.write(str(duty))
        except:
            # 方式2：通过串口发送PWM指令给下位机
            pwm_cmd = f"PWM:{value:03d}"
            self.serial.send(pwm_cmd)
    
    def get_status(self):
        """获取当前补光状态（供UI显示）"""
        return {
            "pwm": self.current_pwm,
            "brightness_pct": int(self.current_pwm / 255 * 100)
        }
```

**硬件方案**：
- LED环形补光灯 + MOSFET驱动电路
- V3的PWM引脚输出 → MOSFET → LED
- 或通过串口发送PWM值给STM32下位机控制

---

### 2.5 加快检测速度（算法层面）

当前瓶颈分析：
- 320x240输入 → YOLO CPU推理 → 每帧约200-500ms
- `time.sleep(0.1)` 在检测循环中额外增加100ms延迟

**优化方案**：

```python
# 优化1：减小输入分辨率（精度换速度）
results = model(frame, imgsz=320)  # 从默认640降到320

# 优化2：跳帧检测
frame_skip = 2  # 每2帧检测1次
frame_count = 0
while running:
    frame_count += 1
    if frame_count % frame_skip != 0:
        continue
    # 执行检测...

# 优化3：ROI裁剪（只检测传送带上的区域）
def crop_roi(frame, x1=50, y1=30, x2=270, y2=210):
    """裁剪感兴趣区域，减少无效计算"""
    return frame[y1:y2, x1:x2]

# 优化4：模型轻量化
# 使用 YOLOv8n (nano) 而不是 YOLOv8s/m
# 或者使用 YOLO-NAS-S，在同等精度下更快

# 优化5：半精度推理（如果支持）
results = model(frame, half=True)  # FP16推理

# 优化6：去掉sleep，用事件驱动
# 将 time.sleep(0.1) 改为 threading.Event.wait(timeout=0.01)
```

---

### 2.6 QT界面完善方案

当前UI问题：
- 界面朴素，只有文字显示
- 没有统计图表
- 没有设置界面
- readme.txt中计划的功能都没实现

**改进设计**：

```python
# gp_mainwindow.py 改进版结构（伪代码）

class MainWindow(QMainWindow):
    def __init__(self):
        # --- 菜单栏 ---
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("设置")
        settings_menu.addAction("模型配置")
        settings_menu.addAction("串口设置")
        settings_menu.addAction("报警阈值")
        
        # --- 顶部工具栏 ---
        # 开始/停止按钮、导出日志按钮、补光调节滑块
        
        # --- 主布局（左中右三栏）---
        # 左栏：双摄像头实时画面（带标注框叠加显示）
        # 中栏：检测结果（大号OK/NG图标 + 当前零件信息）
        # 右栏：统计面板
        #   - 实时良率饼图（matplotlib/pyqtgraph）
        #   - 缺陷分类柱状图
        #   - 检测速度折线图
        #   - 今日统计数字
        
        # --- 底部状态栏 ---
        # 串口状态 | 传送带状态 | 补光PWM | FPS | 模型名称
```

**QSS全局样式升级**：

```python
DARK_THEME = """
QMainWindow {
    background-color: #1a1a2e;
}
QLabel#titleLabel {
    font-size: 28px;
    font-weight: bold;
    color: #e94560;
    padding: 15px;
    background-color: #16213e;
    border-radius: 10px;
}
QPushButton {
    background-color: #0f3460;
    color: #e94560;
    border: 2px solid #e94560;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 14px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #e94560;
    color: white;
}
QPushButton#startBtn {
    background-color: #27ae60;
    border-color: #27ae60;
    color: white;
    font-size: 18px;
    min-height: 50px;
}
QTextEdit {
    background-color: #16213e;
    color: #a8d8ea;
    border: 1px solid #0f3460;
    border-radius: 5px;
    font-family: 'Consolas';
    font-size: 13px;
}
"""
```

---

### 2.7 GPU加速 & 模型转化

#### 当前推理方式

```python
# 当前：CPU推理（ultralytics默认）
model = YOLO("gear.pt")
results = model(frame)  # 在ARM CPU上跑，很慢
```

#### GPU加速方案

SC171 V3 (QCM6490) 的加速方案不是传统的CUDA GPU，而是：

| 方案 | 推理后端 | 加速硬件 | 预估速度提升 |
|------|---------|---------|------------|
| 1. SNPE SDK | .dlc格式 | Hexagon DSP/HTP (NPU) | **5-10x** |
| 2. QNN SDK | .bin/.so格式 | Hexagon HTP (NPU) | **5-10x** |
| 3. Fibo AI Stack | 封装QNN | NPU | **5-10x** |
| 4. ONNX Runtime + QNN EP | .onnx | NPU | **3-5x** |
| 5. TFLite + Hexagon Delegate | .tflite | NPU | **3-5x** |

**推荐路线（Fibo AI Stack）**：

```
gear.pt → gear.onnx → Fibo AI Stack转化 → gear_npu.bin → NPU推理

步骤：
1. PC上: model.export(format="onnx", imgsz=640, simplify=True)
2. PC上: onnxsim gear.onnx gear_sim.onnx
3. V3上: fibo_convert --model gear_sim.onnx --quantize int8 --calib ./calib_data/
4. V3上: 用Fibo AI Stack Python API加载推理
```

**转化后的推理代码**（替换现有ultralytics调用）：

```python
# gp_npu_inference.py - NPU推理封装
import numpy as np
import cv2

class NPUInference:
    """NPU推理引擎（替代ultralytics YOLO）"""
    
    def __init__(self, model_path, conf_threshold=0.6):
        self.conf_threshold = conf_threshold
        self.input_size = (640, 640)
        self.class_names = {0: "good", 1: "bad", 2: "miss", 3: "well"}
        
        # 方式1：Fibo AI Stack
        # from fibo_ai_stack import InferenceEngine
        # self.engine = InferenceEngine(model_path, device="npu")
        
        # 方式2：ONNX Runtime + QNN
        import onnxruntime as ort
        self.session = ort.InferenceSession(
            model_path,
            providers=['QNNExecutionProvider'],
            provider_options=[{'backend_path': 'libQnnHtp.so'}]
        )
        self.input_name = self.session.get_inputs()[0].name
    
    def preprocess(self, frame):
        """预处理"""
        img = cv2.resize(frame, self.input_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC → CHW
        img = np.expand_dims(img, axis=0)    # 添加batch维度
        return img
    
    def postprocess(self, outputs, original_shape):
        """后处理（NMS）"""
        # 解析YOLO输出格式，执行NMS
        # 返回与ultralytics兼容的结果格式
        pass
    
    def __call__(self, frame, conf=None):
        """推理接口（兼容原有调用方式）"""
        conf = conf or self.conf_threshold
        input_data = self.preprocess(frame)
        outputs = self.session.run(None, {self.input_name: input_data})
        results = self.postprocess(outputs, frame.shape)
        return results
```

---

### 2.8 GPU/NPU加速对整个体系的影响

**回答：是的，会对整个体系有显著影响，但都是正面的。**

| 影响层面 | 当前（CPU推理） | NPU加速后 | 需要的改动 |
|---------|---------------|----------|----------|
| **推理速度** | 200-500ms/帧 | 20-50ms/帧 | 修改模型加载和推理代码 |
| **检测循环** | sleep(0.1)足够 | 需要更快的帧获取 | 可提高摄像头分辨率/帧率 |
| **状态机** | 2.3s防抖足够 | 可缩短到0.5-1s | 调整防抖参数 |
| **串口通信** | 9600baud够用 | 可能需要更高频通信 | 可考虑提高波特率 |
| **模型格式** | .pt (PyTorch) | .onnx/.dlc/.bin | 需要重写推理接口 |
| **依赖库** | ultralytics（250MB+） | ONNX Runtime/QNN SDK | 减小部署体积 |
| **代码架构** | model(frame)直接调用 | 需要手写前后处理 | 新增NPU推理模块 |
| **摄像头** | 320x240够用 | 可升到640x480 | 修改CameraQThread |
| **传送带** | 慢速即可 | 可提速 | 硬件调整 |
| **整体吞吐** | ~2件/秒 | **~10-20件/秒** | 产线节拍提升 |

**关键点**：
1. **ultralytics库不能直接用NPU**——必须自己写前后处理
2. **两个模型都需要转化**——gear.pt和final2.pt都要走ONNX→NPU流程
3. **好消息是gear.dlc已经存在**——说明之前已经尝试过SNPE转化
4. **坏消息是UI那些用ultralytics Results对象的代码都要改**——因为NPU推理返回的是原始numpy数组

**建议**：先用ONNX Runtime跑通（改动最小），确认可用后再优化到QNN/Fibo AI Stack。

---

## 第三部分：真实齿轮检测方案

### 3.1 实际工业齿轮检测的典型缺陷

| 缺陷类型 | 描述 | 检测难度 |
|---------|------|---------|
| 缺齿 | 齿轮缺少一个或多个齿 | 低（形状明显异常） |
| 崩齿 | 齿面碎裂 | 中 |
| 磨损 | 齿面磨损变薄 | 高（需要精确测量） |
| 裂纹 | 齿根部微裂纹 | 高（需高分辨率） |
| 毛刺 | 加工残留毛刺 | 中 |
| 锈蚀 | 表面氧化锈蚀 | 低（颜色明显） |
| 尺寸偏差 | 齿距、齿厚不合格 | 高（需精确测量） |
| 黑皮 | 未完全加工的原始表面 | 低 |

### 3.2 真实齿轮检测硬件方案

```
                    ┌─────────────┐
                    │ 环形LED补光灯│
                    │  (可调PWM)   │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │ USB工业相机  │ ← 200W像素以上，全局快门
                    │ (俯视安装)   │
                    └──────┬──────┘
                           │
    ───────────────────────▼─────────────────────── 传送带
    ← 运行方向        [齿轮工位]        → 
                           │
                    ┌──────▼──────┐
                    │  光电传感器  │ ← 触发检测（齿轮到位信号）
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │   SC171 V3   │ ← NPU推理
                    │  (主控制器)  │
                    └──┬────┬─────┘
                       │    │
              RS485/CAN│    │GPIO/PWM
                       │    │
               ┌───────▼┐  ┌▼───────┐
               │PLC/电机 │  │气缸推杆│
               │(传送带) │  │(分拣)  │
               └────────┘  └────────┘
```

### 3.3 具体实施方案

#### 第一阶段：数据采集与标注（2周）

1. **获取齿轮样品**
   - 联系学校机械学院/工厂获取报废齿轮（含各类缺陷）
   - 没有真实缺陷件的话：用锉刀/钳子人为制造缺齿、崩齿缺陷
   - 或者3D打印齿轮模型（含预设缺陷）

2. **搭建拍摄环境**
   - 黑色背景板（消除干扰）
   - 环形LED灯（均匀照明，减少阴影）
   - 固定支架（保持相机位置一致）
   - 拍摄距离约15-20cm

3. **数据采集**
   - 每种缺陷类型拍摄300-500张
   - 变化角度（0°、90°、180°、270°旋转）
   - 变化光照（亮/暗/侧光）
   - 使用数据增强扩充到每类1000+张

4. **标注**
   - 工具：LabelImg 或 Roboflow
   - 标注格式：YOLO格式（txt文件，每行：class x_center y_center width height）
   - 类别：good(合格), broken_tooth(崩齿), missing_tooth(缺齿), rust(锈蚀), burr(毛刺)

#### 第二阶段：模型训练（1周）

```python
# train.py - 在PC上训练（需要GPU）
from ultralytics import YOLO

# 使用YOLOv8n（Nano版，适合端侧部署）
model = YOLO("yolov8n.pt")

results = model.train(
    data="gear_dataset.yaml",   # 数据集配置
    epochs=100,
    imgsz=640,
    batch=16,
    device=0,                    # GPU
    patience=20,                 # 早停
    augment=True,
    mosaic=1.0,
    mixup=0.1,
    name="gear_detection"
)

# 导出ONNX
model.export(format="onnx", imgsz=640, simplify=True)
```

```yaml
# gear_dataset.yaml
path: ./gear_dataset
train: images/train
val: images/val
test: images/test

nc: 5
names:
  0: good
  1: broken_tooth
  2: missing_tooth
  3: rust
  4: burr
```

#### 第三阶段：端侧部署（1周）

```
PC训练好的 best.pt
    │
    ▼ export(format="onnx")
best.onnx
    │
    ▼ onnxsim
best_sim.onnx
    │
    ▼ Fibo AI Stack / QNN SDK 量化转化
best_npu.bin (INT8量化)
    │
    ▼ 部署到V3
NPU推理 → 20-50ms/帧
```

#### 第四阶段：系统集成（2周）

整合所有模块：
1. 光电传感器触发 → GPIO中断 → 开始检测
2. 自适应补光调节 → PWM控制LED
3. NPU推理 → 缺陷分类
4. 状态机决策 → 串口控制分拣
5. 日志记录 → CSV导出
6. 缺陷过多 → 短信报警
7. QT界面实时显示

#### 第五阶段：调试优化（2周）

- 调整检测阈值
- 优化传送带速度与检测节拍匹配
- 补光参数标定
- 边界case处理（齿轮倾斜、重叠等）
- 演示视频录制

### 3.4 硬件BOM清单（真实齿轮方案）

| 物料 | 规格 | 数量 | 预估价格 |
|------|------|------|---------|
| SC171 V3 开发板 | 竞赛版 | 1 | 500-800元 |
| USB工业相机 | 200W像素，全局快门 | 1 | 150-300元 |
| 环形LED补光灯 | 可调亮度，内径>60mm | 1 | 50-100元 |
| MOSFET驱动板 | PWM调光 | 1 | 10元 |
| 光电传感器 | 对射式/漫反射式 | 1 | 15-30元 |
| 小型传送带 | 宽度>100mm，带电机 | 1 | 150-400元 |
| 气缸推杆 | 12V，行程50mm | 1 | 30-60元 |
| 电磁阀 | 控制气缸 | 1 | 20-30元 |
| 亚克力/铝型材支架 | 固定相机和补光灯 | 1套 | 50-100元 |
| 齿轮样品 | 含缺陷件 | 20-30个 | 50-100元 |
| 报警灯 | 三色灯 | 1 | 20元 |
| L610 CAT1模组(可选) | 短信报警用 | 1 | 50-80元 |
| 杜邦线/接线端子 | 若干 | 1批 | 20元 |
| **合计** | | | **约1100-2100元** |

### 3.5 竞赛展示要点

1. **现场演示**：传送带运行 → 齿轮自动到位 → 检测 → 分拣（好品/次品分两个料箱）
2. **界面展示**：实时检测画面 + 良率统计 + 缺陷分布图
3. **技术亮点**：
   - 端侧AI（NPU加速，强调不依赖云端）
   - 双模型流水线（存在性检测→缺陷分类）
   - 自适应补光（根据环境自动调节）
   - 完整工业闭环（检测→决策→执行→日志→报警）
4. **数据展示**：检测速度(FPS)、准确率、良率统计Excel导出

---

## 第四部分：需要你提供的信息

在我开始写具体代码前，请告诉我：

| # | 问题 | 影响范围 |
|---|------|---------|
| 1 | 你现在手上有没有V3开发板？能不能实机调试？ | 决定是否先写PC模拟版 |
| 2 | 你的齿轮样品有了吗？真齿轮还是3D打印的？ | 影响数据集和模型策略 |
| 3 | 你能不能从QQ群拿到Fibo AI Stack SDK？ | 决定NPU部署路线 |
| 4 | 你想先改哪个部分？（UI/状态机/日志/NPU） | 确定开发优先级 |
| 5 | 比赛截止时间是什么时候？ | 确定哪些功能可以砍 |
| 6 | 你的PC有NVIDIA GPU吗？型号是什么？ | 影响模型训练方案 |
| 7 | 传送带和分拣机构已经有了还是需要搭建？ | 影响硬件方案 |

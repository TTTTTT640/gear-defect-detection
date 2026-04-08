"""
自适应补光模块 - 根据环境亮度自动调节补光灯PWM
V3硬件: ADC(光照传感器) + PWM(补光灯)
"""

import cv2
import numpy as np


class LightingController:
    """自适应补光控制器

    原理：分析摄像头帧的平均亮度 → 计算目标PWM占空比 → 通过串口发送给下位机

    V3接口:
      - ADC: 2通道，可接光照传感器(备用方案，当前用图像分析替代)
      - PWM: 1通道，控制补光灯亮度(0~100%)
    """

    def __init__(self, target_brightness=128, min_pwm=0, max_pwm=100):
        """
        Args:
            target_brightness: 目标亮度(0~255)，128为中等亮度
            min_pwm: PWM最小值(%)
            max_pwm: PWM最大值(%)
        """
        self.target = target_brightness
        self.min_pwm = min_pwm
        self.max_pwm = max_pwm

        # 当前状态
        self.current_brightness = 0.0
        self.current_pwm = 0
        self.enabled = True

        # PID参数(简化版，仅用P控制即可满足需求)
        self.kp = 0.5  # 比例系数

        # 防抖：亮度变化超过阈值才更新PWM
        self._last_pwm_sent = -1
        self.pwm_change_threshold = 3  # PWM变化小于3%不更新

    def analyze_brightness(self, frame):
        """分析帧的平均亮度

        Args:
            frame: BGR格式的numpy数组
        Returns:
            float: 平均亮度值 (0~255)
        """
        if frame is None:
            return self.current_brightness
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        self.current_brightness = float(np.mean(gray))
        return self.current_brightness

    def compute_pwm(self, brightness=None):
        """根据亮度计算PWM占空比

        Args:
            brightness: 当前亮度值，None则使用上次分析的值
        Returns:
            int: PWM占空比 (0~100)
        """
        if brightness is None:
            brightness = self.current_brightness

        # 亮度低于目标 → 增加补光(PWM升高)
        # 亮度高于目标 → 减少补光(PWM降低)
        error = self.target - brightness
        pwm = int(self.kp * error)
        pwm = max(self.min_pwm, min(self.max_pwm, pwm))
        self.current_pwm = pwm
        return pwm

    def should_update(self):
        """判断PWM是否需要更新(防抖)"""
        if self._last_pwm_sent < 0:
            return True
        return abs(self.current_pwm - self._last_pwm_sent) >= self.pwm_change_threshold

    def send_pwm(self, serial_manager, pwm=None):
        """通过串口发送PWM指令给下位机

        协议: "PWM:XX" 其中XX为0~100的占空比
        用户可根据实际下位机协议修改此方法。

        Args:
            serial_manager: gp_serial.SerialManager 实例
            pwm: 指定PWM值，None则使用当前计算值
        """
        if pwm is None:
            pwm = self.current_pwm

        if not self.should_update():
            return

        cmd = f"PWM:{pwm:03d}"
        serial_manager.send(cmd)
        self._last_pwm_sent = pwm

    def process_frame(self, frame, serial_manager=None):
        """一站式处理：分析亮度 → 计算PWM → 发送(可选)

        在检测循环中每帧调用此方法即可。

        Args:
            frame: 摄像头帧
            serial_manager: 串口管理器(None则不发送，仅计算)
        Returns:
            tuple: (brightness, pwm)
        """
        if not self.enabled:
            return self.current_brightness, self.current_pwm

        brightness = self.analyze_brightness(frame)
        pwm = self.compute_pwm(brightness)

        if serial_manager and self.should_update():
            self.send_pwm(serial_manager, pwm)

        return brightness, pwm

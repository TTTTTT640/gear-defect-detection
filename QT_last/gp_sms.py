"""
SMS短信报警模块 - 缺陷过多时发送短信通知
支持真实GSM模块(AT指令)和PC模拟模式
"""

import time
import threading
import serial as pyserial


class SmsManager:
    """通过GSM/4G模块发送SMS短信 (AT指令)

    V3开发板通过4G模块支持AT指令发送短信。
    硬件连接后，修改port参数指向实际串口即可。
    """

    def __init__(self, port="/dev/ttyUSB0", baudrate=115200, phone_number=""):
        self.port = port
        self.baudrate = baudrate
        self.phone_number = phone_number
        self.enabled = bool(phone_number)
        self.lock = threading.Lock()
        self.serial = None

        # 冷却机制：发送后5分钟内不重复
        self.cooldown_seconds = 300
        self._last_send_time = 0

        # 报警阈值：连续N个缺陷触发
        self.alert_threshold = 5

    def connect(self):
        """连接GSM模块串口"""
        if not self.enabled:
            return False
        try:
            self.serial = pyserial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=2
            )
            # 测试AT连接
            self.serial.write(b"AT\r\n")
            time.sleep(0.5)
            resp = self.serial.read(self.serial.in_waiting).decode(errors="ignore")
            if "OK" in resp:
                print(f"[SMS] GSM模块连接成功: {self.port}")
                # 设置短信为TEXT模式
                self.serial.write(b"AT+CMGF=1\r\n")
                time.sleep(0.3)
                return True
            else:
                print(f"[SMS] GSM模块无响应: {resp}")
                return False
        except Exception as e:
            print(f"[SMS] 连接失败: {e}")
            return False

    def send_sms(self, message):
        """发送短信

        Args:
            message: 短信内容
        Returns:
            bool: 是否成功
        """
        if not self.enabled or not self.phone_number:
            print("[SMS] 未配置手机号，跳过发送")
            return False

        # 冷却检查
        now = time.time()
        if now - self._last_send_time < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - (now - self._last_send_time))
            print(f"[SMS] 冷却中，{remaining}秒后可再次发送")
            return False

        with self.lock:
            try:
                if self.serial and self.serial.is_open:
                    # AT+CMGS发送短信
                    cmd = f'AT+CMGS="{self.phone_number}"\r\n'
                    self.serial.write(cmd.encode())
                    time.sleep(0.5)
                    self.serial.write(message.encode())
                    self.serial.write(b"\x1a")  # Ctrl+Z 发送
                    time.sleep(3)
                    resp = self.serial.read(self.serial.in_waiting).decode(errors="ignore")
                    if "OK" in resp:
                        print(f"[SMS] 短信发送成功 -> {self.phone_number}: {message}")
                        self._last_send_time = now
                        return True
                    else:
                        print(f"[SMS] 发送失败: {resp}")
                        return False
                else:
                    print("[SMS] 串口未连接")
                    return self.connect() and self.send_sms(message)
            except Exception as e:
                print(f"[SMS] 发送异常: {e}")
                return False

    def check_alert(self, consecutive_defects):
        """检查是否需要发送报警短信

        Args:
            consecutive_defects: 当前连续缺陷数
        Returns:
            bool: 是否触发了报警
        """
        if consecutive_defects >= self.alert_threshold:
            msg = f"[齿轮检测报警] 连续检测到{consecutive_defects}个缺陷品，请检查生产线！"
            return self.send_sms(msg)
        return False

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.close()


class MockSmsManager:
    """PC模拟SMS管理器，仅打印不发送"""

    def __init__(self, phone_number=""):
        self.phone_number = phone_number or "13800000000"
        self.enabled = True
        self.alert_threshold = 5
        self.cooldown_seconds = 300
        self._last_send_time = 0
        self.log = []

    def connect(self):
        print("[SMS-MOCK] 模拟GSM模块已连接")
        return True

    def send_sms(self, message):
        now = time.time()
        if now - self._last_send_time < self.cooldown_seconds:
            remaining = int(self.cooldown_seconds - (now - self._last_send_time))
            print(f"[SMS-MOCK] 冷却中，{remaining}秒后可再次发送")
            return False
        print(f"[SMS-MOCK] -> {self.phone_number}: {message}")
        self.log.append((time.time(), message))
        self._last_send_time = now
        return True

    def check_alert(self, consecutive_defects):
        if consecutive_defects >= self.alert_threshold:
            msg = f"[齿轮检测报警] 连续检测到{consecutive_defects}个缺陷品，请检查生产线！"
            return self.send_sms(msg)
        return False

    def close(self):
        pass

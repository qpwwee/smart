#!/usr/bin/env python3
"""
串口数据处理模块
================
后台线程读取串口数据，解析传感器数值，存入线程安全缓冲区。
无硬件时自动进入 Mock 模式。
"""
import threading
import time
import random
import sys
import os
import json

try:
    import serial
except ImportError:
    serial = None


# ======================================================================
# 线程安全的环形缓冲区
# ======================================================================
class RingBuffer:
    def __init__(self, maxlen=1000):
        self._buffer = []
        self._maxlen = maxlen
        self._lock = threading.Lock()

    def append(self, item):
        with self._lock:
            self._buffer.append(item)
            if len(self._buffer) > self._maxlen:
                self._buffer.pop(0)

    def get_all(self):
        with self._lock:
            return list(self._buffer)

    def get_last(self, n):
        with self._lock:
            return list(self._buffer[-n:])

    def get_latest(self):
        with self._lock:
            return self._buffer[-1] if self._buffer else None

    def clear(self):
        with self._lock:
            self._buffer.clear()

    def __len__(self):
        with self._lock:
            return len(self._buffer)


# ======================================================================
# 传感器数据格式
# ======================================================================
SENSOR_KEYS = ['temperature', 'humidity', 'light', 'fan_status']


def parse_sensor_line(line):
    """
    解析串口数据行
    格式: T:25.50,H:62.30,L:1850,F:0
    返回 dict 或 None
    """
    line = line.strip()
    if not line:
        return None
    parts = line.split(',')
    data = {}
    for part in parts:
        part = part.strip()
        if ':' not in part:
            continue
        key, val = part.split(':', 1)
        key = key.strip().upper()
        val = val.strip()
        if key == 'T':
            try:
                data['temperature'] = round(float(val), 1)
            except ValueError:
                pass
        elif key == 'H':
            try:
                data['humidity'] = round(float(val), 1)
            except ValueError:
                pass
        elif key == 'L':
            try:
                data['light'] = int(float(val))
            except ValueError:
                pass
        elif key == 'F':
            data['fan_status'] = val in ('1', 'true', 'True', 'ON')
    if 'temperature' not in data and 'humidity' not in data and 'light' not in data:
        return None
    data.setdefault('temperature', 0.0)
    data.setdefault('humidity', 0.0)
    data.setdefault('light', 0)
    data.setdefault('fan_status', False)
    return data


# ======================================================================
# Mock 数据生成器
# ======================================================================
class MockSensor:
    """模拟传感器，随机漫步生成合理数据"""

    def __init__(self):
        self.temp = 25.0
        self.humi = 60.0
        self.light = 1500
        self.fan = False

    def read(self):
        # 温度随机漫步 (±0.3°C)，范围 15~40°C
        self.temp += random.uniform(-0.3, 0.3)
        self.temp = max(15, min(40, self.temp))

        # 湿度随机漫步 (±1%)，范围 30~90%
        self.humi += random.uniform(-1, 1)
        self.humi = max(30, min(90, self.humi))

        # 光照随机漫步 (±50 lux)，范围 0~3000
        self.light += random.randint(-50, 50)
        self.light = max(0, min(3000, self.light))

        return {
            'temperature': round(self.temp, 1),
            'humidity': round(self.humi, 1),
            'light': self.light,
            'fan_status': self.fan,
        }


# ======================================================================
# 串口处理器
# ======================================================================
class SerialHandler:
    """
    串口数据处理器。
    在后台线程运行，读取串口数据并存入缓冲区。
    无硬件或串口不可用时自动切换到 Mock 模式。
    """

    def __init__(self, port=None, baudrate=115200, buffer_size=1000):
        self.port = port or self._default_port()
        self.baudrate = baudrate
        self.buffer = RingBuffer(maxlen=buffer_size)
        self._thread = None
        self._running = False
        self._serial = None
        self._mock = None
        self._lock = threading.Lock()
        self._fan_state = False

    def _default_port(self):
        """根据操作系统返回默认串口"""
        if sys.platform == 'win32':
            return 'COM3'
        elif sys.platform == 'darwin':
            return '/dev/tty.usbserial-1420'
        else:
            return '/dev/ttyUSB0'

    def set_fan(self, on: bool):
        """设置风扇状态（发送命令到串口）"""
        self._fan_state = on
        cmd = 'FAN_ON\n' if on else 'FAN_OFF\n'
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(cmd.encode())
                except Exception:
                    pass

    def get_fan(self):
        return self._fan_state

    def start(self):
        """启动后台读取线程"""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """停止后台线程"""
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass

    def wait_for_stop(self, timeout=3):
        """等待线程退出"""
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                # 线程未退出，但进程会继续关闭
                pass

    def _try_open_serial(self):
        """尝试打开真实串口"""
        if serial is None:
            return False
        try:
            ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                timeout=0.5,
            )
            if ser.is_open:
                self._serial = ser
                return True
        except Exception:
            pass
        return False

    def _run(self):
        """后台线程主循环"""
        # 尝试连接硬件
        use_mock = not self._try_open_serial()
        if use_mock:
            self._mock = MockSensor()

        while self._running:
            timestamp = time.time()

            if use_mock:
                # Mock 模式
                data = self._mock.read()
                data['fan_status'] = self._fan_state
                data['_timestamp'] = timestamp
                data['_mock'] = True
                self.buffer.append(data)
                time.sleep(2)
            else:
                # 真实串口模式
                try:
                    line = self._serial.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        data = parse_sensor_line(line)
                        if data:
                            data['_timestamp'] = timestamp
                            data['_mock'] = False
                            data['fan_status'] = self._fan_state
                            self.buffer.append(data)
                except Exception:
                    # 串口异常，切换到 Mock
                    self._mock = MockSensor()
                    use_mock = True
                    try:
                        self._serial.close()
                    except Exception:
                        pass
                    self._serial = None
                time.sleep(0.1)

    def get_latest(self):
        """获取最新一条数据"""
        return self.buffer.get_latest()

    def get_history(self, n=50):
        """获取最近 n 条记录"""
        return self.buffer.get_last(n)

    def is_mock(self):
        """是否在 Mock 模式"""
        latest = self.get_latest()
        return latest.get('_mock', True) if latest else True


# ======================================================================
# 全局单例
# ======================================================================
_handler = None
_handler_lock = threading.Lock()


def get_handler():
    global _handler
    with _handler_lock:
        return _handler


def init_handler(port=None):
    global _handler
    with _handler_lock:
        if _handler is None:
            _handler = SerialHandler(port=port)
            _handler.start()
        return _handler


if __name__ == '__main__':
    # 测试
    h = init_handler()
    time.sleep(5)
    print("最新数据:", h.get_latest())
    print("历史(3条):", h.get_history(3))
    h.stop()

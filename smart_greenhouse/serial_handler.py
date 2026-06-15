#!/usr/bin/env python3
"""
串口数据处理模块
================
后台线程读取串口数据，解析传感器数值，存入线程安全缓冲区。
无硬件时自动进入 Mock 模式。

支持的协议：
  Z-Stack Mesh (GenericApp-DHT11): 12字节二进制包
    字节 0:  0x21 = 同步头
    字节 9:  温度整数 (如 25 = 25°C)
    字节 10: 湿度整数 (如 60 = 60%)
    字节 11: CRC8 校验
"""
import threading
import time
import random
import sys
import os

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
# Z-Stack 二进制协议解析（与 CC2530 GenericApp-DHT11 匹配）
# ======================================================================

SENSOR_KEYS = ['temperature', 'humidity', 'light', 'fan_status']

# Z-Stack 数据包格式常量
ZSTACK_PACKET_SIZE = 12    # 包总长 12 字节
ZSTACK_SYNC_BYTE   = 0x21  # 同步头
ZSTACK_TEMP_IDX    = 9     # 温度索引
ZSTACK_HUMI_IDX    = 10    # 湿度索引
ZSTACK_CRC_IDX     = 11    # CRC 索引


def crc8_zstack(data, length):
    """
    CRC-8 校验，与 Z-Stack GenericApp 的 crc8() 完全一致。
    多项式: x^8 + x^2 + x + 1 (0x07)，初始值 0x00。
    """
    crc = 0
    for i in range(length):
        crc ^= data[i]
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def parse_zstack_packet(packet):
    """
    解析 Z-Stack GenericApp 12字节二进制包。
    
    格式:
      [0]  = 0x21 同步头
      [1]  = 0x02  (固定)
      [2]  = 0x09  (长度标记)
      [3-8]        (地址/命令/标志位，当前未使用)
      [9]  = temp_H  温度整数
      [10] = humidity_H 湿度整数
      [11] = CRC8  校验和
    
    返回 dict 或 None
    """
    if len(packet) < ZSTACK_PACKET_SIZE:
        return None
    if packet[0] != ZSTACK_SYNC_BYTE:
        return None

    # CRC 校验
    calc_crc = crc8_zstack(packet, ZSTACK_CRC_IDX)
    if calc_crc != packet[ZSTACK_CRC_IDX]:
        return None

    temp = packet[ZSTACK_TEMP_IDX]    # 整数 °C
    humi = packet[ZSTACK_HUMI_IDX]    # 整数 %

    return {
        'temperature': round(float(temp), 1),
        'humidity': round(float(humi), 1),
        'light': 0,        # DHT11 无光照传感器
        'fan_status': False,
    }


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

    支持 Z-Stack 二进制协议（CC2530 + DHT11）。
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

    # ── Z-Stack 二进制包读取 ──────────────────────────────

    def _read_zstack_packet(self):
        """
        从串口读取一个完整的 Z-Stack 二进制包。
        策略：逐字节搜索同步头 0x21，找到后读取剩余 11 字节并 CRC 校验。
        自动跳过文本输出（如 "uart0 is OK!\n"）。
        返回 12 字节完整包，或 None（超时/退出）。
        """
        while self._running:
            byte = self._serial.read(1)
            if not byte:
                # 超时返回 None，让主循环继续
                return None
            if byte[0] != ZSTACK_SYNC_BYTE:
                continue  # 跳过非同步字节

            # 读到同步头，尝试读剩余 11 字节
            rest = self._serial.read(ZSTACK_PACKET_SIZE - 1)
            if len(rest) < ZSTACK_PACKET_SIZE - 1:
                # 长度不够，丢弃并继续搜索
                continue

            packet = byte + rest
            # CRC 校验
            if crc8_zstack(packet, ZSTACK_CRC_IDX) == packet[ZSTACK_CRC_IDX]:
                return packet
            # CRC 失败 → 可能是随机字节巧合匹配了 0x21，继续搜
        return None

    def _run(self):
        """后台线程主循环"""
        # 尝试连接硬件
        use_mock = not self._try_open_serial()
        if use_mock:
            self._mock = MockSensor()

        while self._running:
            timestamp = time.time()

            if use_mock:
                # ── Mock 模式 ──
                data = self._mock.read()
                data['fan_status'] = self._fan_state
                data['_timestamp'] = timestamp
                data['_mock'] = True
                self.buffer.append(data)
                time.sleep(2)
            else:
                # ── 真实串口模式（Z-Stack 二进制协议）──
                try:
                    packet = self._read_zstack_packet()
                    if packet:
                        data = parse_zstack_packet(packet)
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

                # 小睡眠：让 read() 的超时来驱动循环
                # 0.5s 的 serial timeout 已足够，这里只做 yield
                time.sleep(0.01)

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

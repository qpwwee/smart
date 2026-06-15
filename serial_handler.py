#!/usr/bin/env python3
"""
串口数据处理模块
================
后台线程读取串口数据，解析 ZigBee 传感器二进制帧，存入线程安全缓冲区。

兼容两种数据格式：
  1. ZigBee 0x21 二进制协议帧（协调器输出，12 字节）
  2. 文本格式 "T:25,H:60,L:1500,F:0"（兼容旧版固件）

无硬件时自动进入 Mock 模式。支持动态端口切换（change_port 方法）。
"""
import threading
import time
import random
import sys

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None
    serial.tools = None


# ======================================================================
# 串口枚举工具
# ======================================================================
def list_serial_ports():
    """
    枚举系统中所有可用的串口，返回 [(port, description), ...] 列表。
    跨平台兼容：Windows / macOS / Linux。
    """
    if serial is None or serial.tools.list_ports is None:
        return []
    ports = []
    for info in serial.tools.list_ports.comports():
        ports.append((info.device, info.description or info.name or info.device))
    return ports


# ======================================================================
# CRC8 校验（与 ZigBee 固件 crc8() 一致：poly 0x07, init 0x00）
# ======================================================================
def crc8(data_bytes):
    crc = 0
    for b in data_bytes:
        crc ^= (b & 0xFF)
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x07) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


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
# 传感器数据解析
# ======================================================================
def parse_sensor_line(line):
    """
    解析文本格式的串口数据行（回退兼容）。
    输入: "T:25,H:60,L:1500,F:0" 或类似格式
    返回: dict 或 None（如果没有解析到任何有效字段）
    """
    line = line.strip()
    if not line:
        return None
    # 过滤不可打印字符（防止二进制帧误入）
    if any(ord(c) < 32 and c not in '\r\n\t' for c in line):
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
            data['fan_status'] = val in ('1', 'true', 'True', 'ON', 'on')
    if 'temperature' not in data and 'humidity' not in data and 'light' not in data:
        return None
    data.setdefault('temperature', 0.0)
    data.setdefault('humidity', 0.0)
    data.setdefault('light', 0)
    data.setdefault('fan_status', False)
    return data


def parse_zigbee_frame(frame_bytes):
    """
    解析 ZigBee 0x21 二进制传感器帧（12 字节）。

    帧格式（来自 C 代码 GenericApp.c）:
      [0]  0x21  帧头
      [1]  0x02  固定标记字节 1
      [2]  0x09  固定标记字节 2（表示数据长度 9）
      [3..8] 固定填充字节
      [9]  temp_H      温度（DHT11 整数部分，uint8，单位℃）
      [10] humidity_H  湿度（DHT11 整数部分，uint8，单位%）
      [11] CRC8        CRC8 校验（基于字节 [0..10]）

    返回 dict 或 None（长度不对 / 帧头不对 / CRC 失败）
    """
    if len(frame_bytes) < 12:
        return None
    if frame_bytes[0] != 0x21:
        return None
    # 验证 CRC8
    expected_crc = crc8(frame_bytes[0:11])
    if frame_bytes[11] != expected_crc:
        return None
    temp = float(frame_bytes[9])
    humi = float(frame_bytes[10])
    return {
        'temperature': temp,
        'humidity': humi,
        'light': 0,
        'fan_status': False,
        '_format': 'zigbee_binary',
    }


def scan_for_zigbee_frame(byte_buffer, start=0):
    """简化版：扫描字节流中首个 0x21 帧，返回 (dict, new_offset)。"""
    blen = len(byte_buffer)
    i = start
    while i <= blen - 12:
        if byte_buffer[i] == 0x21 and byte_buffer[i + 1] == 0x02 and byte_buffer[i + 2] == 0x09:
            frame = bytes(byte_buffer[i:i + 12])
            result = parse_zigbee_frame(frame)
            if result is not None:
                return result, i + 12
        i += 1
    # 保留尾部最多 11 字节作为可能的不完整帧
    keep_start = max(0, blen - 11)
    return None, keep_start


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
        self.temp += random.uniform(-0.3, 0.3)
        self.temp = max(15, min(40, self.temp))
        self.humi += random.uniform(-1, 1)
        self.humi = max(30, min(90, self.humi))
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
    串口数据处理器。在后台线程运行：
      1. 从串口读取原始字节 → 累积到内部缓冲
      2. 尝试扫描 0x21 二进制 ZigBee 帧
      3. 如果二进制扫描没有结果，尝试按换行解析文本协议
      4. 解析结果存入 RingBuffer，供 GUI 读取

    支持动态端口切换（change_port）。无硬件时自动进入 Mock 模式。
    """

    STATE_IDLE       = 'idle'
    STATE_MOCK       = 'mock'
    STATE_CONNECTING = 'connecting'
    STATE_CONNECTED  = 'connected'

    # 二进制/文本缓冲上限（防止内存无限增长）
    _MAX_BUF_BYTES = 256
    _MAX_TEXT_CHARS = 1024

    def __init__(self, port=None, baudrate=115200, buffer_size=1000):
        self.baudrate = baudrate
        self.buffer = RingBuffer(maxlen=buffer_size)
        self._thread = None
        self._running = False
        self._serial = None
        self._mock = None
        self._lock = threading.Lock()
        self._fan_state = False
        # 连接状态
        self._port = None
        self._state = self.STATE_IDLE
        self._connect_error = None
        # 统计与调试信息（线程安全：仅由后台线程写，主线程读）
        self._stats = {
            'bytes_received': 0,   # 累计接收字节数
            'binary_frames': 0,    # 成功解析的 0x21 帧
            'crc_failures': 0,     # CRC 校验失败次数
            'text_lines': 0,       # 成功解析的文本行
            'last_activity': 0.0,  # 最近一次接收数据的时间戳
            'first_bytes_hex': '', # 首次收到的字节 (HEX 转储)
        }
        self._stats_lock = threading.Lock()

        # 如果传入了 port，立即切换；否则 Mock 模式
        if port:
            self.change_port(port)
        else:
            self._start_mock()

    def _start_mock(self):
        self._mock = MockSensor()
        self._state = self.STATE_MOCK
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    # ---- public API ----
    def set_fan(self, on: bool):
        self._fan_state = on
        cmd = b'FAN_ON\n' if on else b'FAN_OFF\n'
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(cmd)
                except Exception:
                    pass

    def get_fan(self):
        return self._fan_state

    def get_state(self):
        return self._state

    def get_connect_error(self):
        return self._connect_error

    def get_current_port(self):
        return self._port

    def is_mock(self):
        return self._state == self.STATE_MOCK

    def get_stats(self):
        """返回一份统计快照（供 UI 显示调试信息）。"""
        with self._stats_lock:
            return dict(self._stats)

    def change_port(self, new_port):
        """切换端口：停止线程 → 关闭旧串口 → 打开新端口 → 重启线程。"""
        # 1. 停止现有线程
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        # 2. 关闭旧串口
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

        # 3. 清空缓冲与统计
        self.buffer.clear()
        self._frame_sync = False
        self._reset_stats()

        # 4. 切换模式
        if new_port is None:
            self._state = self.STATE_MOCK
            self._mock = MockSensor()
            self._port = None
            self._connect_error = None
            print('[模式] 切换到 Mock 模拟模式')
        else:
            self._state = self.STATE_CONNECTING
            opened = self._do_open_port(new_port)
            if opened:
                self._state = self.STATE_CONNECTED
            else:
                self._state = self.STATE_MOCK
                self._mock = MockSensor()
                self._port = None
                print('[模式] 端口打开失败，自动切换到 Mock 模拟模式')

        # 5. 重启后台线程
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
        if self._serial:
            try:
                self._serial.close()
            except Exception:
                pass

    def wait_for_stop(self, timeout=3):
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    # ---- 内部实现 ----
    def _do_open_port(self, port):
        if serial is None:
            self._connect_error = 'pyserial 未安装'
            return False
        try:
            ser = serial.Serial(
                port=port,
                baudrate=self.baudrate,
                timeout=0.5,
            )
            if ser.is_open:
                self._serial = ser
                self._port = port
                self._connect_error = None
                print(f'[串口] {port} @ {self.baudrate} 已连接')
                return True
        except Exception as e:
            self._connect_error = str(e)
            print(f'[错误] 无法打开串口 {port}: {e}')
        return False

    def _reset_stats(self):
        with self._stats_lock:
            self._stats = {
                'bytes_received': 0,
                'binary_frames': 0,
                'crc_failures': 0,
                'text_lines': 0,
                'last_activity': 0.0,
                'first_bytes_hex': '',
            }

    def _record_stats(self, key, inc=1):
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + inc

    def _record_activity(self, raw_bytes):
        """记录接收到的原始字节，更新统计信息（首次还会做 HEX 转储）。"""
        with self._stats_lock:
            self._stats['bytes_received'] += len(raw_bytes)
            self._stats['last_activity'] = time.time()
            if not self._stats['first_bytes_hex'] and len(raw_bytes) > 0:
                self._stats['first_bytes_hex'] = ' '.join(f'{b:02X}' for b in raw_bytes[:32])
                print(f'[串口] 收到 {len(raw_bytes)} 字节: {self._stats["first_bytes_hex"]}')

    # ---- 二进制帧扫描（修复版）----
    def _scan_buffer_for_frames(self, byte_buf):
        """
        扫描字节缓冲区，提取所有 0x21 格式的有效帧。
        返回 (frames 列表, 保留的未消费字节)。

        修复内容：
        1. 正确保留 consumed 之后的所有未消费字节
        2. 对 CRC 失败但帧头匹配的字节做容错（跳过 1 字节继续扫描）
        3. 仅在缓冲超过 _MAX_BUF_BYTES 时截断，避免累积垃圾
        """
        frames = []
        blen = len(byte_buf)
        i = 0

        while i <= blen - 12:
            if byte_buf[i] == 0x21:
                # 快速过滤：检查后续固定标记字节
                if byte_buf[i + 1] == 0x02 and byte_buf[i + 2] == 0x09:
                    # 可能是有效帧 → 验证 CRC
                    frame_slice = bytes(byte_buf[i:i + 12])
                    expected = crc8(frame_slice[0:11])
                    if frame_slice[11] == expected:
                        parsed = parse_zigbee_frame(frame_slice)
                        if parsed is not None:
                            frames.append(parsed)
                            i += 12
                            continue
                    else:
                        # CRC 失败：这是一个可能是帧头但数据损坏的位置
                        self._record_stats('crc_failures', 1)
            # 默认前进 1 字节继续扫描
            i += 1

        # 保留 i 之后的字节（可能是尚未完整到达的一帧）
        remaining = bytearray(byte_buf[i:])
        # 防无限增长（仅保留最后 _MAX_BUF_BYTES 字节作为尾部）
        if len(remaining) > self._MAX_BUF_BYTES:
            remaining = remaining[-self._MAX_BUF_BYTES:]
        return frames, remaining

    # ---- 文本协议扫描（回退兼容）----
    def _try_parse_text(self, byte_buf):
        """
        在剩余字节中查找 '\n' 或 '\r'，作为文本协议解析。
        仅在二进制扫描没有结果时作为回退调用。
        返回 (parsed_dict_list, 剩余未消费字节)
        """
        results = []
        # 搜索所有完整行（以 \r 或 \n 结尾）
        text = byte_buf.decode('ascii', errors='replace')
        lines = []
        buf_tail = bytearray()
        # 按 \n 或 \r 分割
        for line in text.splitlines():
            line = line.strip()
            if line:
                lines.append(line)
        # 保留无法形成完整行的尾部字节（下次继续累积）
        last_cr = text.rfind('\n')
        if last_cr == -1:
            # 没有完整行：全部留给下次
            buf_tail = bytearray(byte_buf)
            lines = []
        else:
            # 丢弃已处理的前缀；保留尾部不完整行的字节
            buf_tail = bytearray()

        for line in lines:
            parsed = parse_sensor_line(line)
            if parsed:
                parsed['_format'] = 'text'
                results.append(parsed)

        # 文本缓冲过大时强制截断
        if len(buf_tail) > self._MAX_TEXT_CHARS:
            buf_tail = buf_tail[-self._MAX_TEXT_CHARS:]
        return results, buf_tail

    def _run(self):
        """后台线程主循环"""
        use_mock = (self._state == self.STATE_MOCK)
        if use_mock:
            print('[模式] Mock 模拟模式')

        byte_buf = bytearray()      # 二进制帧扫描缓冲
        text_buf = bytearray()      # 文本协议回退缓冲

        while self._running:
            timestamp = time.time()

            if use_mock:
                # Mock 数据
                data = self._mock.read()
                data['fan_status'] = self._fan_state
                data['_timestamp'] = timestamp
                data['_mock'] = True
                self.buffer.append(data)
                time.sleep(2)
                continue

            # ——— 真实串口模式 ———
            try:
                waiting = self._serial.in_waiting
                if waiting > 0:
                    raw = self._serial.read(waiting)
                    byte_buf.extend(raw)
                    text_buf.extend(raw)
                    self._record_activity(raw)

                # 1. 优先二进制扫描
                parsed_frames, byte_buf = self._scan_buffer_for_frames(byte_buf)
                if parsed_frames:
                    for frame in parsed_frames:
                        frame['fan_status'] = self._fan_state
                        frame['_timestamp'] = timestamp
                        frame['_mock'] = False
                        self.buffer.append(frame)
                        self._record_stats('binary_frames', 1)
                        with self._stats_lock:
                            if not self._stats.get('first_binary_ts'):
                                self._stats['first_binary_ts'] = timestamp
                    text_buf = bytearray()  # 有二进制结果就清空文本缓冲
                    # 短暂让出
                    time.sleep(0.1)
                    continue

                # 2. 回退：尝试文本协议解析
                text_results, text_buf = self._try_parse_text(text_buf)
                if text_results:
                    for frame in text_results:
                        frame['fan_status'] = self._fan_state
                        frame['_timestamp'] = timestamp
                        frame['_mock'] = False
                        self.buffer.append(frame)
                        self._record_stats('text_lines', 1)
                    time.sleep(0.1)
                    continue

            except (serial.SerialException, OSError) as e:
                print(f'[错误] 串口异常: {e}')
                with self._lock:
                    self._mock = MockSensor()
                    self._state = self.STATE_MOCK
                    use_mock = True
                try:
                    self._serial.close()
                except Exception:
                    pass
                self._serial = None
                self.buffer.clear()
                print('[模式] 已切换至 Mock 模拟模式')
                continue
            except Exception as e:
                print(f'[错误] 未知异常: {e}')
                time.sleep(0.1)
                continue

            # 串口无数据或未解析出结果时短暂休眠
            time.sleep(0.05)

    def get_latest(self):
        return self.buffer.get_latest()

    def get_history(self, n=50):
        return self.buffer.get_last(n)


# ======================================================================
# 全局单例（支持动态端口切换）
# ======================================================================
_handler = None
_handler_lock = threading.Lock()


def get_handler():
    global _handler
    with _handler_lock:
        return _handler


def init_handler(port=None):
    """
    初始化全局串口处理器单例。

    - port=None: 默认启动 Mock 模式（无硬件演示）
    - port='COM3': 连接到指定端口
    - 已有实例时：动态切换端口
    """
    global _handler
    with _handler_lock:
        if _handler is None:
            _handler = SerialHandler(port=port)
        else:
            if port != _handler.get_current_port():
                _handler.change_port(port)
        return _handler


if __name__ == '__main__':
    # 快速测试：枚举所有可用串口
    ports = list_serial_ports()
    print('可用串口:')
    for p, desc in ports:
        print(f'  {p}  ({desc})')
    if not ports:
        print('  （无）')

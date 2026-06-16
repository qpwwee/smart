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


def parse_zigbee_frame(frame_bytes, sensor_type=0x01):
    """
    解析 ZigBee 0x21 二进制传感器帧（12 字节）。

    帧格式（来自 C 代码 GenericApp.c）:
      [0]  0x21  帧头
      [1]  0x02  固定标记字节 1 (DHT11) / 0x03 (光照)
      [2]  0x09  固定标记字节 2（表示数据长度 9）
      [3..8] 固定填充字节
      [9..10] 传感器数据
      [11] CRC8

    sensor_type: 0x01 = 温湿度 (DHT11), 0x02 = 光照, 0x00 = 未知
      - 0x01: byte[9]=温度, byte[10]=湿度
      - 0x02: byte[9..10]=16-bit 光照值 (大端)

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
    result = {
        'temperature': 0.0,
        'humidity': 0.0,
        'light': 0,
        'fan_status': False,
        '_format': 'zigbee_binary',
        '_sensor_type': sensor_type,
    }
    if sensor_type == 0x02:  # 光照传感器
        result['light'] = (frame_bytes[9] << 8) | frame_bytes[10]
    else:  # 温湿度 (DHT11) 或未知（向后兼容）
        result['temperature'] = float(frame_bytes[9])
        result['humidity'] = float(frame_bytes[10])
    return result


def scan_for_zigbee_frame(byte_buffer, start=0):
    """
    扫描字节流中首个 ZigBee 帧。

    新协议（协调器转发）：1 字节 type 标识 + 12 字节原 0x21 帧 = 13 字节
    旧协议（直连/无 type）：12 字节 0x21 帧

    帧结构（原 12 字节）:
      [0]  0x21  帧头
      [1]  0x02 (DHT11) / 0x03 (光照)  传感器标记
      [2]  0x09  固定
      [3..10] 传感器数据
      [11] CRC8
    """
    blen = len(byte_buffer)
    i = start
    # 1) 先按 13 字节协议扫描 (带 type 前缀)
    while i <= blen - 13:
        if (byte_buffer[i] in (0x00, 0x01, 0x02) and
                byte_buffer[i + 1] == 0x21 and
                byte_buffer[i + 2] in (0x02, 0x03) and
                byte_buffer[i + 3] == 0x09):
            sensor_type = byte_buffer[i]
            frame_bytes = bytes(byte_buffer[i + 1:i + 13])
            result = parse_zigbee_frame(frame_bytes, sensor_type)
            if result is not None:
                return result, i + 13
        i += 1
    # 2) 回退: 12 字节旧协议 (无 type 前缀)
    i = start
    while i <= blen - 12:
        if (byte_buffer[i] == 0x21 and
                byte_buffer[i + 1] in (0x02, 0x03) and
                byte_buffer[i + 2] == 0x09):
            frame_bytes = bytes(byte_buffer[i:i + 12])
            result = parse_zigbee_frame(frame_bytes, 0x01)  # 默认按 DHT11
            if result is not None:
                return result, i + 12
        i += 1
    # 保留尾部最多 12 字节作为可能的不完整帧
    keep_start = max(0, blen - 12)
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
        self._led_state = False
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
        # 数据节流控制
        self._last_frame_time = 0
        self._min_frame_interval = 1.0  # 最小帧间隔（秒），每秒最多1帧

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
        # 风扇控制指令（十六进制）
        if on:
            cmd = bytes([0x21, 0x01, 0x09, 0x01, 0x5A, 0x40, 0x2C, 0x66, 0x24, 0x31, 0xA8])
        else:
            cmd = bytes([0x21, 0x01, 0x09, 0x01, 0x5A, 0x40, 0x2C, 0x66, 0x24, 0x30, 0xAF])
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(cmd)
                except Exception:
                    pass

    def get_fan(self):
        return self._fan_state

    def set_led(self, on: bool):
        """RGB LED 控制：开/关白光"""
        self._led_state = on
        if on:
            cmd = bytes([0x21, 0x03, 0x09, 0x01, 0x5A, 0x40, 0x19, 0x6C, 0x55, 0xFF, 0xFF, 0xFF])
        else:
            cmd = bytes([0x21, 0x03, 0x09, 0x01, 0x5A, 0x40, 0x2D, 0x6C, 0x55, 0x00, 0x00, 0x00])
        with self._lock:
            if self._serial and self._serial.is_open:
                try:
                    self._serial.write(cmd)
                except Exception:
                    pass

    def get_led(self):
        return self._led_state

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

        支持两种协议：
        1. 新协议（协调器转发）：1 字节 type 标识 + 12 字节原 0x21 帧 = 13 字节
        2. 旧协议（直连）：12 字节 0x21 帧

        帧结构（原 12 字节）:
          [0]  0x21  帧头
          [1]  0x02 (DHT11) / 0x03 (光照)  传感器标记
          [2]  0x09  固定
          [3..10] 传感器数据
          [11] CRC8
        """
        frames = []
        blen = len(byte_buf)
        i = 0

        # 1) 先扫 13 字节协议 (带 type 前缀)
        while i <= blen - 13:
            if (byte_buf[i] in (0x00, 0x01, 0x02) and
                    byte_buf[i + 1] == 0x21 and
                    byte_buf[i + 2] in (0x02, 0x03) and
                    byte_buf[i + 3] == 0x09):
                sensor_type = byte_buf[i]
                frame_slice = bytes(byte_buf[i + 1:i + 13])
                expected = crc8(frame_slice[0:11])
                if frame_slice[11] == expected:
                    parsed = parse_zigbee_frame(frame_slice, sensor_type)
                    if parsed is not None:
                        frames.append(parsed)
                        i += 13
                        continue
                else:
                    self._record_stats('crc_failures', 1)
            i += 1

        # 2) 回退: 扫 12 字节旧协议 (无 type 前缀)
        j = 0
        while j <= blen - 12:
            if (byte_buf[j] == 0x21 and
                    byte_buf[j + 1] in (0x02, 0x03) and
                    byte_buf[j + 2] == 0x09):
                frame_slice = bytes(byte_buf[j:j + 12])
                expected = crc8(frame_slice[0:11])
                if frame_slice[11] == expected:
                    parsed = parse_zigbee_frame(frame_slice, 0x01)
                    if parsed is not None:
                        # 避免与新协议已解析的帧重复
                        already = any(
                            abs(f.get('_ts_offset', 0) - j) < 12 for f in frames
                        )
                        if not already:
                            frames.append(parsed)
                        j += 12
                        continue
                else:
                    self._record_stats('crc_failures', 1)
            j += 1

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

                # 数据节流：检查是否应该处理新数据
                should_process = (timestamp - self._last_frame_time) >= self._min_frame_interval

                # 1. 优先二进制扫描
                parsed_frames, byte_buf = self._scan_buffer_for_frames(byte_buf)
                if parsed_frames and should_process:
                    # 只取最后一帧，丢弃中间的帧（节流）
                    frame = parsed_frames[-1]
                    frame['fan_status'] = self._fan_state
                    frame['_timestamp'] = timestamp
                    frame['_mock'] = False
                    self.buffer.append(frame)
                    self._record_stats('binary_frames', 1)
                    with self._stats_lock:
                        if not self._stats.get('first_binary_ts'):
                            self._stats['first_binary_ts'] = timestamp
                    self._last_frame_time = timestamp
                    text_buf = bytearray()  # 有二进制结果就清空文本缓冲
                    # 短暂让出
                    time.sleep(0.1)
                    continue

                # 2. 回退：尝试文本协议解析
                text_results, text_buf = self._try_parse_text(text_buf)
                if text_results and should_process:
                    # 只取最后一行
                    frame = text_results[-1]
                    frame['fan_status'] = self._fan_state
                    frame['_timestamp'] = timestamp
                    frame['_mock'] = False
                    self.buffer.append(frame)
                    self._record_stats('text_lines', 1)
                    self._last_frame_time = timestamp
                    time.sleep(0.1)
                    continue

                # 如果没有处理数据但有新数据到达，清空缓冲区防止堆积
                if not should_process and (parsed_frames or text_results):
                    byte_buf.clear()
                    text_buf.clear()

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

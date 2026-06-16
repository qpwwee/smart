#!/usr/bin/env python3
"""
智能温室监控系统 - 原生桌面应用
===============================
美观的桌面 GUI，双击直接运行。
技术栈: Python + Tkinter + matplotlib
"""
import tkinter as tk
from tkinter import ttk
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import threading
import time
from datetime import datetime
import os
import sys

# ── 中文字体 ─────────────────────────────────────
_CN_FONTS = ['PingFang HK', 'PingFang SC', 'Heiti TC', 'STHeiti', 'Apple LiGothic', 'Arial Unicode MS']
plt.rcParams['font.sans-serif'] = _CN_FONTS + ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
_FONT = _CN_FONTS[0]  # tkinter 字体

from serial_handler import init_handler, get_handler, list_serial_ports

# ── 颜色主题（现代深色） ────────────────────────────
C = {
    'bg':          '#0d1117',
    'card':        '#161b22',
    'card_hover':  '#1c2333',
    'border':      '#30363d',
    'divider':     '#21262d',
    'text':        '#e6edf3',
    'text_dim':    '#8b949e',
    'text_muted':  '#6e7681',
    'accent':      '#58a6ff',
    'green':       '#3fb950',
    'red':         '#f85149',
    'orange':      '#d29922',
    'purple':      '#bc8cff',
    'pink':        '#f778ba',

    'temp':        '#ff6b6b',
    'humi':        '#4ecdc4',
    'light':       '#ffd93d',

    'chart_grid':  '#21262d',
    'chart_bg':    '#0d1117',
}

# ── 传感器配置 ──────────────────────────────────────
SENSOR_CONFIG = [
    { 'key': 'temperature', 'label': '温度',   'unit': '°C',  'fmt': '{:.1f}',
      'color': C['temp'],  'icon': '🌡',  'good': (20, 30) },
    { 'key': 'humidity',    'label': '湿度',   'unit': '%',   'fmt': '{:.1f}',
      'color': C['humi'],  'icon': '💧',  'good': (45, 70) },
    { 'key': 'light',       'label': '光照',   'unit': 'lux', 'fmt': '{}',
      'color': C['light'], 'icon': '☀',  'good': (500, 2500) },
]


# ======================================================================
# 工具: 圆角矩形 Canvas 方法
# ======================================================================
def _round_rect(canvas, x1, y1, x2, y2, r=12, **kwargs):
    """在 Canvas 上画圆角矩形"""
    points = [x1+r, y1, x2-r, y1, x2-r, y1, x2, y1, x2, y1+r,
              x2, y2-r, x2, y2-r, x2, y2, x2-r, y2,
              x1+r, y2, x1, y2, x1, y2-r,
              x1, y1+r, x1, y1, x1+r, y1]
    return canvas.create_polygon(points, smooth=True, **kwargs)


# ======================================================================
# 自定义按钮类（圆角 + 悬停效果）
# ======================================================================
class RoundButton(tk.Canvas):
    def __init__(self, parent, text='', fg='#fff', bg=C['card'],
                 hover_bg=C['card_hover'], accent=C['accent'],
                 command=None, font_size=12, width=160, height=42):
        super().__init__(parent, width=width, height=height,
                         bg=C['bg'], highlightthickness=0)
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._accent = accent
        self._fg = fg
        self._text = text
        self._font = (_FONT, font_size, 'bold')
        self._ww = width
        self._hh = height

        # 左侧彩色装饰条（更醒目）
        self._accent_id = _round_rect(self, 4, 8, 8, height-8,
                                       r=3, fill=accent, outline='')

        # 背景
        self._bg_id = _round_rect(self, 2, 2, width-2, height-2,
                                  r=8, fill=bg, outline='')

        # 文字（居中）
        self._text_id = self.create_text(width//2, height//2,
                                         text=text, fill=fg,
                                         font=self._font)

        # 事件绑定
        self.tag_bind(self._bg_id, '<Enter>', self._on_enter)
        self.tag_bind(self._text_id, '<Enter>', self._on_enter)
        self.tag_bind(self._bg_id, '<Leave>', self._on_leave)
        self.tag_bind(self._text_id, '<Leave>', self._on_leave)
        self.tag_bind(self._bg_id, '<Button-1>', self._on_click)
        self.tag_bind(self._text_id, '<Button-1>', self._on_click)

        self.configure(cursor='hand2')

    def _on_enter(self, event):
        self.itemconfig(self._bg_id, fill=self._hover_bg)

    def _on_leave(self, event):
        self.itemconfig(self._bg_id, fill=self._bg)

    def _on_click(self, event):
        if self._command:
            self._command()

    def set_text(self, text):
        self._text = text
        self.itemconfig(self._text_id, text=text)

    def set_accent(self, color):
        self._accent = color
        self.itemconfig(self._accent_id, fill=color)


# ======================================================================
# 主窗口
# ======================================================================
class SmartGreenhouseApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('智能温室监控系统')
        self.root.geometry('1320x860')
        self.root.minsize(1060, 700)
        self.root.configure(bg=C['bg'])

        # 设图标
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.icns')
        try:
            self.root.iconbitmap(default=icon_path)
        except Exception:
            pass

        # 初始化串口处理器（默认 Mock 模式，用户选择端口后切换）
        init_handler(port=None)
        self.handler = get_handler()

        # 构建
        self._build_ui()
        self._refresh_ports()
        self._update_timer()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ── 构建 UI ──────────────────────────────────────
    def _build_ui(self):
        root = self.root

        # ─ 主容器 ─
        self.mf = tk.Frame(root, bg=C['bg'])
        self.mf.pack(fill='both', expand=True, padx=24, pady=20)

        # ─ 顶栏 ─
        self._build_header(self.mf)

        # ─ 三张传感器卡片 ─
        self._build_cards(self.mf)

        # ─ 控制栏 ─
        self._build_controls(self.mf)

        # ─ 图表区 ─
        self._build_charts(self.mf)

        # ─ 底部状态栏 ─
        self._build_statusbar(self.mf)

    # ── 顶栏 ─────────────────────────────────────
    def _build_header(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 18))

        # 标题 + 图标
        icon = tk.Label(frame, text='  🌿', font=(_FONT, 22),
                        bg=C['bg'], fg=C['green'])
        icon.pack(side='left')

        title = tk.Label(frame, text='智能温室监控系统', font=(_FONT, 18, 'bold'),
                         bg=C['bg'], fg=C['text'])
        title.pack(side='left', padx=(4, 0))

        # 版本
        ver = tk.Label(frame, text='v1.0', font=(_FONT, 9),
                       bg=C['bg'], fg=C['text_muted'])
        ver.pack(side='left', padx=(8, 0), pady=(6, 0))

        # 右侧: 连接状态
        status_frame = tk.Frame(frame, bg=C['bg'])
        status_frame.pack(side='right')

        self._status_dot = tk.Canvas(status_frame, width=10, height=10,
                                     bg=C['bg'], highlightthickness=0)
        self._status_dot.pack(side='left', padx=(0, 6))
        self._dot_id = self._status_dot.create_oval(1, 1, 9, 9,
                                                     fill=C['orange'], outline='')

        self.status_label = tk.Label(status_frame, text='连接中...',
                                     font=(_FONT, 10), bg=C['bg'], fg=C['orange'])
        self.status_label.pack(side='left')

    # ── 传感器卡片 ────────────────────────────────
    def _build_cards(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 16))

        self._cards = {}
        for cfg in SENSOR_CONFIG:
            card = self._make_card(frame, cfg)
            card['frame'].pack(side='left', fill='both', expand=True, padx=5)
            self._cards[cfg['key']] = card

    def _make_card(self, parent, cfg):
        color = cfg['color']
        
        # 外框（带阴影效果）
        outer = tk.Frame(parent, bg=C['bg'], bd=0)
        
        # 阴影层
        shadow = tk.Canvas(outer, width=380, height=160,
                          bg=C['bg'], highlightthickness=0, bd=0)
        shadow.pack(fill='both', expand=True, padx=2, pady=2)
        
        # 绘制阴影
        shadow.create_rectangle(8, 8, 388, 168, fill='#000000', stipple='gray25')
        
        # 主卡片画布
        canvas = tk.Canvas(shadow, width=380, height=160,
                          bg=C['card'], highlightthickness=0, bd=0)
        canvas.place(x=0, y=0)
        
        # 顶部彩色装饰条（渐变效果）
        for i in range(6):
            alpha = 1.0 - i * 0.15
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            r = int(r * alpha)
            g = int(g * alpha)
            b = int(b * alpha)
            tint = f'#{r:02x}{g:02x}{b:02x}'
            canvas.create_rectangle(0, i, 400, i+1, fill=tint, outline='')
        
        # 图标背景圆
        icon_bg = canvas.create_oval(18, 18, 58, 58, fill=color, outline='')
        canvas.itemconfig(icon_bg, stipple='gray50')
        
        # 图标
        canvas.create_text(38, 38, text=cfg['icon'],
                          font=(_FONT, 18), anchor='center', fill='#ffffff')
        
        # 标签
        canvas.create_text(70, 30, text=cfg['label'],
                          font=(_FONT, 12, 'bold'), anchor='w', fill=C['text_dim'])
        
        # 大数值
        val_id = canvas.create_text(30, 85, text='--',
                                   font=(_FONT, 42, 'bold'),
                                   anchor='w', fill=C['text'])
        
        # 单位
        unit_id = canvas.create_text(220, 95, text=cfg['unit'],
                                    font=(_FONT, 14),
                                    anchor='w', fill=C['text_dim'])
        
        # 状态指示（带背景）
        status_bg = canvas.create_rectangle(20, 130, 120, 150, 
                                           fill=color, outline='', stipple='gray25')
        status_id = canvas.create_text(70, 140, text='等待数据...',
                                      font=(_FONT, 10, 'bold'),
                                      anchor='center', fill='#ffffff')
        
        return {
            'frame': outer,
            'val_id': val_id,
            'unit_id': unit_id,
            'status_id': status_id,
            'status_bg': status_bg,
            'canvas': canvas,
            'cfg': cfg,
        }

    # ── 控制栏 ─────────────────────────────────
    def _build_controls(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 12))

        # ── 端口选择区 ─────────────────────────────
        port_frame = tk.Frame(frame, bg=C['bg'])
        port_frame.pack(side='left', padx=(0, 16))

        port_label = tk.Label(port_frame, text='端口:',
                             font=(_FONT, 11), bg=C['bg'], fg=C['text_dim'])
        port_label.pack(side='left', padx=(0, 6))

        # 端口下拉框
        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(port_frame, textvariable=self._port_var,
                                         font=(_FONT, 11), width=40,
                                         state='readonly')
        self._port_combo.pack(side='left', padx=(0, 8))

        # 刷新按钮
        self._refresh_btn = RoundButton(port_frame, text='🔄 刷新',
                                        bg=C['card'], hover_bg=C['card_hover'],
                                        accent=C['accent'], fg=C['text'],
                                        command=self._on_refresh_ports,
                                        font_size=11, width=90, height=40)
        self._refresh_btn.pack(side='left', padx=(0, 6))

        # 连接按钮
        self._connect_btn = RoundButton(port_frame, text='🔗 连接',
                                        bg=C['accent'], hover_bg='#4c9aed',
                                        accent=C['green'], fg='#fff',
                                        command=self._on_connect_click,
                                        font_size=12, width=100, height=42)
        self._connect_btn.pack(side='left', padx=(0, 6))

        # Mock 模式切换按钮
        self._mock_btn = RoundButton(port_frame, text='🎭 模拟',
                                     bg=C['card'], hover_bg=C['card_hover'],
                                     accent=C['orange'], fg=C['text'],
                                     command=self._on_mock_click,
                                     font_size=11, width=90, height=40)
        self._mock_btn.pack(side='left', padx=(6, 0))

        # ── 右侧：风扇 + 清空 ───────────────────────
        right_frame = tk.Frame(frame, bg=C['bg'])
        right_frame.pack(side='right')

        # 风扇按钮（自定义圆角）
        self.fan_btn = RoundButton(right_frame, text='🔛 风扇: 关闭',
                                   bg=C['card'], hover_bg=C['card_hover'],
                                   accent=C['purple'], fg=C['text'],
                                   command=self._toggle_fan,
                                   font_size=13, width=180, height=44)
        self.fan_btn.pack(side='left', padx=(0, 12))

        # 风扇状态灯
        self.fan_dot = tk.Canvas(right_frame, width=12, height=12,
                                 bg=C['bg'], highlightthickness=0)
        self.fan_dot.pack(side='left')
        self._fd_off = self.fan_dot.create_oval(1, 1, 11, 11,
                                                fill=C['text_muted'], outline='')
        self._fd_on = self.fan_dot.create_oval(1, 1, 11, 11,
                                               fill=C['green'], outline='',
                                               state='hidden')

        # RGB LED 按钮
        self.led_btn = RoundButton(right_frame, text='💡 灯光: 关闭',
                                   bg=C['card'], hover_bg=C['card_hover'],
                                   accent=C['orange'], fg=C['text'],
                                   command=self._toggle_led,
                                   font_size=13, width=180, height=44)
        self.led_btn.pack(side='left', padx=(12, 12))

        # LED 状态灯
        self.led_dot = tk.Canvas(right_frame, width=12, height=12,
                                 bg=C['bg'], highlightthickness=0)
        self.led_dot.pack(side='left')
        self._ld_off = self.led_dot.create_oval(1, 1, 11, 11,
                                                fill=C['text_muted'], outline='')
        self._ld_on = self.led_dot.create_oval(1, 1, 11, 11,
                                               fill=C['orange'], outline='',
                                               state='hidden')

        # 清空数据
        self.clear_btn = RoundButton(right_frame, text='🗑 清空数据',
                                     bg=C['card'], hover_bg=C['card_hover'],
                                     accent=C['red'], fg=C['text'],
                                     command=self._clear_data,
                                     font_size=12, width=150, height=42)
        self.clear_btn.pack(side='left', padx=(12, 0))

    # ── 图表区 ─────────────────────────────────
    def _build_charts(self, parent):
        container = tk.Frame(parent, bg=C['bg'])
        container.pack(fill='both', expand=True, pady=(0, 8))

        self.figures = {}
        titles = [
            ('🌡 温度趋势', 'temperature', C['temp'], '°C'),
            ('💧 湿度趋势', 'humidity', C['humi'], '%'),
        ]

        for title, key, color, unit in titles:
            row = tk.Frame(container, bg=C['bg'])
            row.pack(fill='both', expand=True, pady=3)

            fig = Figure(figsize=(8, 1.6), dpi=92)
            fig.patch.set_facecolor(C['chart_bg'])

            ax = fig.add_subplot(111)
            ax.set_facecolor(C['chart_bg'])

            # 标题
            ax.set_title(title, color=C['text_dim'], fontsize=8.5,
                         fontfamily=_FONT, pad=5, loc='left')
            ax.set_ylabel(unit, color=C['text_muted'], fontsize=7,
                          fontfamily=_FONT, labelpad=1)

            # 移除上右 spine
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color(C['divider'])
            ax.spines['left'].set_linewidth(0.5)
            ax.spines['bottom'].set_color(C['divider'])
            ax.spines['bottom'].set_linewidth(0.5)

            ax.tick_params(colors=C['text_muted'], labelsize=6.5)
            ax.grid(True, alpha=0.3, color=C['chart_grid'], linewidth=0.4)

            # 渐变填充
            line, = ax.plot([], [], color=color, linewidth=1.6,
                            antialiased=True, alpha=0.95)
            ax.fill_between([], [], alpha=0.08, color=color)
            self._fill_collection = None

            ax.set_xlim(0, 60)
            ax.set_ylim(0, 100)

            canvas = FigureCanvasTkAgg(fig, master=row)
            canvas.draw()
            canvas.get_tk_widget().pack(fill='both', expand=True)

            self.figures[key] = {
                'fig': fig, 'ax': ax, 'line': line,
                'canvas': canvas, 'fill': None,
            }

    # ── 底部状态栏 ─────────────────────────────
    def _build_statusbar(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(6, 0))

        self.time_label = tk.Label(frame, text='等待传感器数据...',
                                   font=(_FONT, 9), bg=C['bg'], fg=C['text_muted'])
        self.time_label.pack(side='left')

        self.count_label = tk.Label(frame, text='',
                                    font=(_FONT, 9), bg=C['bg'], fg=C['text_muted'])
        self.count_label.pack(side='right')

    # ── 端口控制 ─────────────────────────────────
    def _refresh_ports(self):
        """扫描并更新串口下拉列表"""
        ports = list_serial_ports()
        if ports:
            self._port_combo['values'] = [f'{p}  ({d})' for p, d in ports]
            self._port_combo.current(0)
        else:
            self._port_combo['values'] = ['（未检测到串口设备）']
            self._port_combo.current(0)
            self._port_combo['state'] = 'disabled'

    def _on_refresh_ports(self):
        """刷新端口列表按钮"""
        self._port_combo['state'] = 'readonly'
        self._refresh_ports()

    def _on_connect_click(self):
        """连接按钮：切换到选定端口"""
        selection = self._port_var.get()
        if not selection or '（未检测到' in selection:
            return
        # 提取端口名（去掉描述部分，取第一个空格前的内容）
        port = selection.split()[0]
        self.handler.change_port(port)
        # 清空之前 Mock 模式的数据
        self._clear_data()

    def _on_mock_click(self):
        """切换到 Mock 模拟模式"""
        self.handler.change_port(None)
        self._clear_data()

    # ── 风扇控制 ────────────────────────────────────
    def _toggle_fan(self):
        fan = self.handler.get_fan()
        self.handler.set_fan(not fan)

    def _update_fan_ui(self, on):
        if on:
            self.fan_btn.set_text('🔛 风扇: 开启')
            self.fan_btn.set_accent(C['green'])
            self.fan_dot.itemconfig(self._fd_on, state='normal')
            self.fan_dot.itemconfig(self._fd_off, state='hidden')
        else:
            self.fan_btn.set_text('🔛 风扇: 关闭')
            self.fan_btn.set_accent(C['purple'])
            self.fan_dot.itemconfig(self._fd_on, state='hidden')
            self.fan_dot.itemconfig(self._fd_off, state='normal')

    # ── RGB LED 控制 ─────────────────────────────────
    def _toggle_led(self):
        led = self.handler.get_led()
        self.handler.set_led(not led)

    def _update_led_ui(self, on):
        if on:
            self.led_btn.set_text('💡 灯光: 开启')
            self.led_btn.set_accent(C['green'])
            self.led_dot.itemconfig(self._ld_on, state='normal')
            self.led_dot.itemconfig(self._ld_off, state='hidden')
        else:
            self.led_btn.set_text('💡 灯光: 关闭')
            self.led_btn.set_accent(C['orange'])
            self.led_dot.itemconfig(self._ld_on, state='hidden')
            self.led_dot.itemconfig(self._ld_off, state='normal')

    def _clear_data(self):
        self.handler.buffer.clear()
        for key in self.figures:
            info = self.figures[key]
            info['line'].set_data([], [])
            if info['fill']:
                info['fill'].remove()
                info['fill'] = None

    # ── 定时刷新 ────────────────────────────────────
    def _update_timer(self):
        try:
            self._refresh()
        except Exception:
            pass
        self.root.after(2000, self._update_timer)

    def _refresh(self):
        latest = self.handler.get_latest()
        history = self.handler.get_history(120)

        if latest is None:
            self.status_label.config(text='等待传感器数据...', fg=C['orange'])
            self._status_dot.itemconfig(self._dot_id, fill=C['orange'])
            return

        # ── 连接状态 ─
        state = self.handler.get_state()
        is_mock = latest.get('_mock', True)

        if state == 'connecting':
            self.status_label.config(text='正在连接...', fg=C['orange'])
            self._status_dot.itemconfig(self._dot_id, fill=C['orange'])
        elif state == 'connected':
            port = self.handler.get_current_port() or ''
            self.status_label.config(text=f'已连接 {port}', fg=C['green'])
            self._status_dot.itemconfig(self._dot_id, fill=C['green'])
        elif is_mock:
            self.status_label.config(text='模拟模式（无硬件）', fg=C['orange'])
            self._status_dot.itemconfig(self._dot_id, fill=C['orange'])
        else:
            self.status_label.config(text='已连接', fg=C['green'])
            self._status_dot.itemconfig(self._dot_id, fill=C['green'])

        # ─ 更新卡片 ─
        for cfg in SENSOR_CONFIG:
            key = cfg['key']
            card = self._cards[key]
            val = latest.get(key, 0)

            # 大数值
            val_text = cfg['fmt'].format(val)
            card['canvas'].itemconfig(card['val_id'], text=val_text)

            # 状态文字 + 颜色
            lo, hi = cfg['good']
            if lo <= val <= hi:
                status_text = '● 正常'
                status_color = C['green']
            elif val < lo * 0.8 or val > hi * 1.2:
                status_text = '● 异常'
                status_color = C['red']
            else:
                status_text = '● 偏高' if val > hi else '● 偏低'
                status_color = C['orange']

            card['canvas'].itemconfig(card['status_id'],
                                      text=status_text, fill='#ffffff')
            card['canvas'].itemconfig(card['status_bg'], fill=status_color)

        # ─ 风扇 ─
        self._update_fan_ui(latest.get('fan_status', False))

        # ─ LED ─
        self._update_led_ui(self.handler.get_led())

        # ─ 时间戳 ─
        ts = latest.get('_timestamp', time.time())
        dt = datetime.fromtimestamp(ts)
        self.time_label.config(text=f'最后更新 · {dt.strftime("%H:%M:%S")}')
        self.count_label.config(text=f'已记录 {len(history)} 条数据')

        # ─ 图表 ─
        if len(history) >= 2:
            indices = list(range(len(history)))

            for cfg in SENSOR_CONFIG:
                key = cfg['key']
                info = self.figures[key]
                vals = [h.get(key, 0) for h in history]

                info['line'].set_data(indices, vals)

                # 更新填充
                if info['fill']:
                    info['fill'].remove()
                info['fill'] = info['ax'].fill_between(
                    indices, vals, alpha=0.08, color=cfg['color']
                )

                # 动态范围
                info['ax'].set_xlim(0, max(len(indices), 60))
                vmin, vmax = min(vals), max(vals)
                margin = max((vmax - vmin) * 0.25, 3)
                info['ax'].set_ylim(vmin - margin, vmax + margin)
                info['canvas'].draw()

    # ── 关闭 ────────────────────────────────────────
    def _on_close(self):
        self.handler.stop()
        self.handler.wait_for_stop(timeout=2)
        self.root.quit()
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self._on_close()


# ======================================================================
# 入口
# ======================================================================
def main():
    """
    启动智能温室监控系统。
    启动后默认进入 Mock 模拟模式，可在界面左上角选择串口端口后点击"连接"来连接硬件。
    """
    # 初始化串口处理器（默认 Mock 模式，等待用户在 GUI 中选择端口）
    try:
        init_handler(port=None)
    except Exception as e:
        print(f'[错误] 初始化失败: {e}')
        sys.exit(1)

    app = SmartGreenhouseApp()
    app.run()


if __name__ == '__main__':
    main()

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

# ── 颜色主题（现代深色 / 分层） ─────────────────────
C = {
    'bg':             '#0f1419',
    'card':           '#1a1f2b',
    'card_hover':     '#222a38',
    'card_border':    '#2a3346',
    'card_border_hi': '#3d4a60',
    'divider':        '#1c222d',
    'text':           '#e8ecf2',
    'text_strong':    '#f5f7fa',
    'text_dim':       '#8a94a6',
    'text_muted':     '#5c6370',
    'accent':         '#4f8cff',
    'accent_hover':   '#4078e0',
    'green':          '#4caf50',
    'red':            '#ef5350',
    'orange':         '#f5a623',
    'purple':         '#a084ff',
    'pink':           '#f472b6',

    'temp':           '#ff6b6b',
    'humi':           '#4ecdc4',
    'light':          '#ffd93d',

    'chart_bg':       '#1a1f2b',
    'chart_grid':     '#2a3346',
}

# ── 传感器配置 ──────────────────────────────────────
SENSOR_CONFIG = [
    { 'key': 'temperature', 'label': '温度',   'unit': '°C',  'fmt': '{:.1f}',
      'color': C['temp'],  'icon': '🌡',  'good': (20, 30) },
    { 'key': 'humidity',    'label': '湿度',   'unit': '%',   'fmt': '{:.1f}',
      'color': C['humi'],  'icon': '💧',  'good': (45, 70) },
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
# 自定义按钮类（圆角 + 边框 + 悬停效果）
# ======================================================================
class RoundButton(tk.Canvas):
    def __init__(self, parent, text='', fg=None, bg=C['card'],
                 hover_bg=C['card_hover'], accent=C['accent'],
                 command=None, font_size=12, width=160, height=42):
        if fg is None:
            fg = C['text']
        super().__init__(parent, width=width, height=height,
                         bg=parent['bg'] if isinstance(parent, (tk.Frame, tk.Canvas)) and 'bg' in parent.keys() else C['bg'],
                         highlightthickness=0)
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._accent = accent
        self._fg = fg
        self._text = text
        self._font = (_FONT, font_size, 'bold')
        self._ww = width
        self._hh = height

        # 外层边框（与主色一致的 1px 细线）
        self._border_id = _round_rect(self, 1, 1, width - 1, height - 1,
                                       r=8, fill=accent, outline='')

        # 背景（内缩 1px 制造边框感）
        self._bg_id = _round_rect(self, 2, 2, width - 2, height - 2,
                                  r=7, fill=bg, outline='')

        # 左侧彩色装饰条（与 accent 一致，细边）
        self._accent_id = _round_rect(self, 2, 6, 6, height - 6,
                                       r=2, fill=accent, outline='')

        # 文字（居中）
        self._text_id = self.create_text(width // 2, height // 2,
                                        text=text, fill=fg,
                                        font=(_FONT, font_size, 'bold'))

        # 事件绑定（绑定到整个 canvas，避免点击死角）
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)
        self.bind('<Button-1>', self._on_click)

        self.configure(cursor='hand2')

    def _on_enter(self, event):
        self.itemconfig(self._bg_id, fill=self._hover_bg)
        self.itemconfig(self._border_id, fill=self._accent)

    def _on_leave(self, event):
        self.itemconfig(self._bg_id, fill=self._bg)
        self.itemconfig(self._border_id, fill=self._accent)

    def _on_click(self, event):
        if self._command:
            self._command()

    def set_text(self, text):
        self._text = text
        self.itemconfig(self._text_id, text=text)

    def set_accent(self, color):
        self._accent = color
        self.itemconfig(self._accent_id, fill=color)
        self.itemconfig(self._border_id, fill=color)


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
        frame.pack(fill='x', pady=(0, 20))

        # 左侧彩色标识条
        bar = tk.Canvas(frame, width=4, height=56, bg=C['bg'], highlightthickness=0)
        bar.pack(side='left', padx=(0, 14))
        bar.create_rectangle(0, 0, 4, 56, fill=C['green'], outline='')

        # 标题区域（两行：大标题 + 副标题）
        title_wrap = tk.Frame(frame, bg=C['bg'])
        title_wrap.pack(side='left')

        title = tk.Label(title_wrap, text='智能温室监控系统',
                         font=(_FONT, 18, 'bold'),
                         bg=C['bg'], fg=C['text_strong'])
        title.pack(anchor='w')

        sub = tk.Label(title_wrap, text='Smart Greenhouse Monitor · 实时环境数据与设备控制',
                       font=(_FONT, 10),
                       bg=C['bg'], fg=C['text_muted'])
        sub.pack(anchor='w', pady=(2, 0))

        # 版本 badge
        ver_label = tk.Label(frame, text=' v1.0 ',
                            font=(_FONT, 9, 'bold'),
                            bg=C['card'], fg=C['text_muted'])
        ver_label.pack(side='left', padx=16, pady=(20, 0))

        # 右侧: 连接状态 pill
        status_frame = tk.Frame(frame, bg=C['bg'])
        status_frame.pack(side='right')

        # 状态 pill 容器
        pill_canvas = tk.Canvas(status_frame, width=200, height=38,
                               bg=C['bg'], highlightthickness=0)
        pill_canvas.pack(pady=(8, 0))
        _round_rect(pill_canvas, 0, 0, 200, 38, r=19,
                     fill=C['card'], outline='')

        # 状态指示圆点
        self._status_dot = tk.Canvas(pill_canvas, width=12, height=12,
                                     bg=C['card'], highlightthickness=0)
        self._status_dot.place(x=12, y=13)
        self._dot_id = self._status_dot.create_oval(1, 1, 11, 11,
                                                     fill=C['orange'], outline='')

        # 状态文字
        self.status_label = tk.Label(pill_canvas, text='等待连接',
                                     font=(_FONT, 10, 'bold'),
                                     bg=C['card'], fg=C['orange'])
        self.status_label.place(x=32, y=10)

    # ── 传感器卡片 ────────────────────────────────
    def _build_cards(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 16))

        self._cards = {}
        for cfg in SENSOR_CONFIG:
            card = self._make_card(frame, cfg)
            card['frame'].pack(side='left', fill='both', expand=True, padx=5)
            self._cards[cfg['key']] = card

        # 控制卡片（代替原来的光照卡片）
        ctrl_card = self._make_control_card(frame)
        ctrl_card.pack(side='left', fill='both', expand=True, padx=5)

    def _make_card(self, parent, cfg):
        color = cfg['color']

        # 卡片外框（双层边框，模拟投影感）
        outer = tk.Frame(parent, bg=C['bg'], bd=0)
        outer.configure(highlightbackground=C['card_border_hi'], highlightthickness=0)

        canvas = tk.Canvas(outer, width=360, height=150,
                          bg=C['card'], highlightthickness=1,
                          highlightbackground=C['card_border'])
        canvas.pack(fill='both', expand=True, padx=0, pady=0)

        # 顶部彩色装饰条（4px 渐变）
        canvas.create_rectangle(0, 0, 360, 4, fill=color, outline='')
        canvas.create_rectangle(0, 4, 360, 6, fill=color, outline='')

        # 图标背景圆（半透明填充，纯色圆+内阴影感）
        canvas.create_oval(20, 18, 66, 64, fill=color, outline='')

        # 图标
        canvas.create_text(43, 41, text=cfg['icon'],
                          font=(_FONT, 20), anchor='center', fill='#ffffff')

        # 标签（在图标右侧，大字号）
        canvas.create_text(78, 26, text=cfg['label'],
                          font=(_FONT, 13, 'bold'), anchor='w', fill=C['text_strong'])
        canvas.create_text(78, 48, text='real-time',
                          font=(_FONT, 9), anchor='w', fill=C['text_muted'])

        # 大数值（左对齐，放大字号 40）
        val_id = canvas.create_text(28, 100, text='--',
                                   font=(_FONT, 42, 'bold'),
                                   anchor='w', fill=C['text_strong'])

        # 单位（数值右侧
        unit_id = canvas.create_text(250, 105, text=cfg['unit'],
                                    font=(_FONT, 14, 'bold'),
                                    anchor='w', fill=C['text_dim'])

        # 状态 pill（底部）
        status_bg = _round_rect(canvas, 22, 128, 22 + 110, 146,
                                  r=8, fill=color, outline='')
        status_id = canvas.create_text(77, 137, text='等待数据...',
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

    def _make_control_card(self, parent):
        color = C['purple']

        outer = tk.Frame(parent, bg=C['bg'], bd=0)
        outer.configure(highlightthickness=0)

        canvas = tk.Canvas(outer, width=360, height=150,
                          bg=C['card'], highlightthickness=1,
                          highlightbackground=C['card_border'])
        canvas.pack(fill='both', expand=True, padx=0, pady=0)

        # 顶部彩色装饰条（与传感器卡片一致）
        canvas.create_rectangle(0, 0, 360, 4, fill=color, outline='')
        canvas.create_rectangle(0, 4, 360, 6, fill=color, outline='')

        # 图标背景圆
        canvas.create_oval(20, 18, 66, 64, fill=color, outline='')

        # 图标
        canvas.create_text(43, 41, text='⚙',
                          font=(_FONT, 20), anchor='center', fill='#ffffff')

        # 标签
        canvas.create_text(78, 26, text='设备控制',
                          font=(_FONT, 13, 'bold'), anchor='w', fill=C['text_strong'])
        canvas.create_text(78, 48, text='relay',
                          font=(_FONT, 9), anchor='w', fill=C['text_muted'])

        # 控制按钮区域（2 按钮并列）
        fan_wrap = tk.Frame(canvas, bg=C['card'])
        fan_wrap.place(x=10, y=72)

        self.fan_btn = RoundButton(fan_wrap, text='🔛 风扇: 关闭',
                                   bg=C['bg'], hover_bg=C['card_hover'],
                                   accent=C['purple'], fg=C['text_strong'],
                                   command=self._toggle_fan,
                                   font_size=12, width=150, height=44)
        self.fan_btn.pack(side='left', padx=(10, 6))

        self.fan_dot = tk.Canvas(fan_wrap, width=14, height=14,
                                 bg=C['card'], highlightthickness=0)
        self.fan_dot.pack(side='left', padx=(0, 0), pady=14)
        self._fd_off = self.fan_dot.create_oval(1, 1, 13, 13,
                                                fill=C['text_muted'], outline='')
        self._fd_on = self.fan_dot.create_oval(1, 1, 13, 13,
                                               fill=C['green'], outline='',
                                               state='hidden')

        led_wrap = tk.Frame(canvas, bg=C['card'])
        led_wrap.place(x=180, y=72)

        self.led_btn = RoundButton(led_wrap, text='💡 灯光: 关闭',
                                   bg=C['bg'], hover_bg=C['card_hover'],
                                   accent=C['orange'], fg=C['text_strong'],
                                   command=self._toggle_led,
                                   font_size=12, width=150, height=44)
        self.led_btn.pack(side='left', padx=(0, 6))

        self.led_dot = tk.Canvas(led_wrap, width=14, height=14,
                                 bg=C['card'], highlightthickness=0)
        self.led_dot.pack(side='left', padx=0, pady=14)
        self._ld_off = self.led_dot.create_oval(1, 1, 13, 13,
                                                fill=C['text_muted'], outline='')
        self._ld_on = self.led_dot.create_oval(1, 1, 13, 13,
                                               fill=C['orange'], outline='',
                                               state='hidden')

        return outer

    # ── 控制栏 ─────────────────────────────────
    def _build_controls(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=16)

        # ── 左侧：端口选择区 ───────────────────────
        port_frame = tk.Frame(frame, bg=C['bg'])
        port_frame.pack(side='left')

        # 端口下拉框
        self._port_var = tk.StringVar()
        self._port_combo = ttk.Combobox(port_frame, textvariable=self._port_var,
                                         font=(_FONT, 11), width=38,
                                         state='readonly')
        self._port_combo.pack(side='left', padx=(0, 10))

        # 刷新按钮
        self._refresh_btn = RoundButton(port_frame, text='🔄 刷新端口',
                                        bg=C['card'], hover_bg=C['card_hover'],
                                        accent=C['accent'], fg=C['text_strong'],
                                        command=self._on_refresh_ports,
                                        font_size=11, width=110, height=40)
        self._refresh_btn.pack(side='left', padx=(0, 8))

        # 连接按钮（更突出，绿色）
        self._connect_btn = RoundButton(port_frame, text='🔗 连接',
                                       bg=C['accent'], hover_bg=C['accent_hover'],
                                       accent=C['green'], fg=C['text_strong'],
                                       command=self._on_connect_click,
                                       font_size=11, width=110, height=40)
        self._connect_btn.pack(side='left', padx=(0, 8))

        # 模拟模式按钮
        self._mock_btn = RoundButton(port_frame, text='🎭 模拟',
                                      bg=C['card'], hover_bg=C['card_hover'],
                                      accent=C['orange'], fg=C['text_strong'],
                                      command=self._on_mock_click,
                                      font_size=11, width=110, height=40)
        self._mock_btn.pack(side='left', padx=0)

        # ── 右侧：清空数据 ───────────────────────
        right_frame = tk.Frame(frame, bg=C['bg'])
        right_frame.pack(side='right')

        self.clear_btn = RoundButton(right_frame, text='🗑 清空数据',
                                     bg=C['card'], hover_bg=C['card_hover'],
                                     accent=C['red'], fg=C['text_strong'],
                                     command=self._clear_data,
                                     font_size=11, width=130, height=40)
        self.clear_btn.pack(side='left', padx=(12, 0))

    # ── 图表区 ─────────────────────────────────
    def _build_charts(self, parent):
        container = tk.Frame(parent, bg=C['bg'])
        container.pack(fill='both', expand=True, pady=(8, 12))

        self.figures = {}
        titles = [
            ('温度趋势 (°C)', 'temperature', C['temp'], '°C'),
            ('湿度趋势 (%)', 'humidity', C['humi'], '%'),
        ]

        for title, key, color, unit in titles:
            row = tk.Frame(container, bg=C['bg'])
            row.pack(fill='both', expand=True, pady=8)

            fig = Figure(figsize=(10, 2.4), dpi=100)
            fig.patch.set_facecolor(C['chart_bg'])

            ax = fig.add_subplot(111)
            ax.set_facecolor(C['chart_bg'])

            # 标题 - 现代粗体
            ax.set_title(title, color=C['text_strong'], fontsize=11,
                         fontweight='bold', pad=8, loc='left')
            ax.set_ylabel(unit, color=C['text_dim'], fontsize=9,
                          labelpad=6)

            # 美化 spines
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color(C['card_border'])
            ax.spines['left'].set_linewidth(0.7)
            ax.spines['bottom'].set_color(C['card_border'])
            ax.spines['bottom'].set_linewidth(0.7)

            # 美化刻度
            ax.tick_params(colors=C['text_muted'], labelsize=8,
                          length=3, width=0.5)

            # 更细腻的网格线
            ax.grid(True, alpha=0.25, color=C['card_border'],
                   linewidth=0.5, linestyle='--')

            # 平滑曲线 + 半透明填充
            line, = ax.plot([], [], color=color, linewidth=2.2,
                           antialiased=True, alpha=0.95)
            ax.fill_between([], [], alpha=0.12, color=color)
            self._fill_collection = None

            # Y 轴自适应
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
        frame.pack(fill='x', pady=(8, 0))

        # 顶部分隔细线
        sep = tk.Frame(frame, height=1, bg=C['card_border'])
        sep.pack(fill='x', side='top')

        status_wrap = tk.Frame(frame, bg=C['bg'])
        status_wrap.pack(fill='x', pady=(8, 0))

        self.time_label = tk.Label(status_wrap, text='等待传感器数据...',
                                   font=(_FONT, 10),
                                   bg=C['bg'], fg=C['text_muted'])
        self.time_label.pack(side='left')

        self.count_label = tk.Label(status_wrap, text='',
                                    font=(_FONT, 10),
                                    bg=C['bg'], fg=C['text_muted'])
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

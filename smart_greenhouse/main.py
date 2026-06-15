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

from serial_handler import init_handler, get_handler

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

    'temp':        '#f85149',
    'humi':        '#58a6ff',
    'light':       '#d29922',

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
                 command=None, font_size=11, width=140, height=36):
        super().__init__(parent, width=width, height=height,
                         bg=C['bg'], highlightthickness=0)
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._accent = accent
        self._fg = fg
        self._text = text
        self._font = (_FONT, font_size)
        self._ww = width
        self._hh = height

        # 加速条（底部彩色线）
        self._accent_id = _round_rect(self, 2, height-4, width-2, height-2,
                                       r=2, fill=accent, outline='')

        # 背景
        self._bg_id = _round_rect(self, 2, 2, width-2, height-6,
                                  r=10, fill=bg, outline='')

        # 文字
        self._text_id = self.create_text(width//2, (height-4)//2,
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

        self.handler = get_handler()

        # 构建
        self._build_ui()
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

        # 外框
        outer = tk.Frame(parent, bg=C['border'], bd=0)
        # 内层画布
        canvas = tk.Canvas(outer, width=380, height=160,
                           bg=C['card'], highlightthickness=0, bd=0)
        canvas.pack(fill='both', expand=True)

        # 顶部彩色装饰线
        canvas.create_rectangle(0, 0, 400, 4, fill=color, outline='')

        # 图标 + 标签
        canvas.create_text(24, 24, text=cfg['icon'],
                           font=(_FONT, 16), anchor='w', fill=C['text'])

        canvas.create_text(52, 26, text=cfg['label'],
                           font=(_FONT, 11), anchor='w', fill=C['text_dim'])

        # 大数值
        val_id = canvas.create_text(24, 70, text='--',
                                    font=(_FONT, 38, 'bold'),
                                    anchor='w', fill=C['text'])

        # 单位
        unit_id = canvas.create_text(200, 84, text=cfg['unit'],
                                     font=(_FONT, 13),
                                     anchor='w', fill=C['text_dim'])

        # 状态指示
        status_id = canvas.create_text(24, 124, text='等待数据...',
                                       font=(_FONT, 9),
                                       anchor='w', fill=C['text_muted'])

        # 底部彩色条（渐变感）
        for i in range(8):
            alpha = 1.0 - i * 0.12
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            r = int(r + (0x0d - r) * (1 - alpha))
            g = int(g + (0x11 - g) * (1 - alpha))
            b = int(b + (0x17 - b) * (1 - alpha))
            tint = f'#{r:02x}{g:02x}{b:02x}'
            canvas.create_rectangle(0, 156 + i, 400, 157 + i,
                                    fill=tint, outline='')

        return {
            'frame': outer,
            'val_id': val_id,
            'unit_id': unit_id,
            'status_id': status_id,
            'canvas': canvas,
            'cfg': cfg,
        }

    # ── 控制栏 ─────────────────────────────────
    def _build_controls(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 12))

        # 风扇按钮（自定义圆角）
        self.fan_btn = RoundButton(frame, text='🔛 风扇: 关闭',
                                   bg=C['card'], hover_bg=C['card_hover'],
                                   accent=C['purple'], fg=C['text'],
                                   command=self._toggle_fan,
                                   font_size=12, width=170, height=38)
        self.fan_btn.pack(side='left', padx=(0, 10))

        # 风扇状态灯
        self.fan_dot = tk.Canvas(frame, width=12, height=12,
                                 bg=C['bg'], highlightthickness=0)
        self.fan_dot.pack(side='left')
        self._fd_off = self.fan_dot.create_oval(1, 1, 11, 11,
                                                fill=C['text_muted'], outline='')
        self._fd_on = self.fan_dot.create_oval(1, 1, 11, 11,
                                               fill=C['green'], outline='',
                                               state='hidden')

        # 温度单位切换
        self.clear_btn = RoundButton(frame, text='🗑 清空数据',
                                     bg=C['card'], hover_bg=C['card_hover'],
                                     accent=C['red'], fg=C['text'],
                                     command=self._clear_data,
                                     font_size=11, width=130, height=34)
        self.clear_btn.pack(side='right')

    # ── 图表区 ─────────────────────────────────
    def _build_charts(self, parent):
        container = tk.Frame(parent, bg=C['bg'])
        container.pack(fill='both', expand=True, pady=(0, 8))

        self.figures = {}
        titles = [
            ('🌡 温度趋势', 'temperature', C['temp'], '°C'),
            ('💧 湿度趋势', 'humidity', C['humi'], '%'),
            ('☀ 光照趋势', 'light', C['light'], 'lux'),
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

        # ─ 状态 ─
        is_mock = latest.get('_mock', True)
        if is_mock:
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

            # ─ 特殊处理：DHT11 无光照传感器 ─
            if key == 'light' and not is_mock and val == 0:
                val_text = 'N/A'
                card['canvas'].itemconfig(card['val_id'], text=val_text)
                card['canvas'].itemconfig(card['status_id'],
                                          text='无光照传感器', fill=C['text_muted'])
                continue

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
                                      text=status_text, fill=status_color)

        # ─ 风扇 ─
        self._update_fan_ui(latest.get('fan_status', False))

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

                # ─ 硬件模式下光照全零时跳过绘图 ─
                if key == 'light' and not is_mock and all(v == 0 for v in vals):
                    info['line'].set_data([], [])
                    if info['fill']:
                        info['fill'].remove()
                        info['fill'] = None
                    continue

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
    try:
        init_handler()
    except Exception as e:
        print(f'[错误] 串口初始化失败: {e}')
        sys.exit(1)

    app = SmartGreenhouseApp()
    app.run()


if __name__ == '__main__':
    main()

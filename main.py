#!/usr/bin/env python3
"""
GREEN HOUSE - Cyberpunk Wasteland Edition
==========================================
A cyberpunk-themed greenhouse monitoring system with wasteland aesthetics.
Features: Neon colors, glitch effects, scanlines, terminal-style UI.
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

# ── Fonts ─────────────────────────────────────
_CN_FONTS = ['PingFang HK', 'PingFang SC', 'Heiti TC', 'STHeiti', 'Apple LiGothic', 'Arial Unicode MS']
plt.rcParams['font.sans-serif'] = _CN_FONTS + ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
_FONT = _CN_FONTS[0]
_MONO = 'Courier'  # Monospace for cyberpunk feel

from serial_handler import init_handler, get_handler, list_serial_ports

# ── Cyberpunk Wasteland Color Theme ────────────────────────────
C = {
    # Backgrounds
    'bg':          '#0a0a0a',  # Pure black
    'bg_alt':      '#0d0d0d',  # Slightly lighter
    'card':        '#1a1a1a',  # Dark gray
    'card_hover':  '#252525',  # Hover state
    'border':      '#333333',  # Border
    'divider':     '#1f1f1f',  # Divider

    # Neon colors
    'neon_green':  '#00ff9c',  # Primary neon
    'neon_cyan':   '#00ffff',  # Cyan
    'neon_magenta':'#ff00ff',  # Magenta
    'neon_yellow': '#ffff00',  # Warning yellow
    'neon_red':    '#ff0066',  # Error red
    'neon_orange': '#ff6600',  # Orange

    # Text
    'text':        '#00ff9c',  # Primary text (neon green)
    'text_dim':    '#00cc7a',  # Dimmed text
    'text_muted':  '#008855',  # Muted text
    'text_white':  '#ffffff',  # White text

    # Sensor colors (neon variants)
    'temp':        '#ff0066',  # Hot pink/red
    'humi':        '#00ffff',  # Cyan
    'light':       '#ffff00',  # Yellow

    # Chart
    'chart_grid':  '#1f1f1f',
    'chart_bg':    '#0a0a0a',
}

# ── Sensor Config ──────────────────────────────────────
SENSOR_CONFIG = [
    { 'key': 'temperature', 'label': 'TEMP',   'unit': '°C',  'fmt': '{:.1f}',
      'color': C['temp'],  'icon': '▲',  'good': (20, 30) },
    { 'key': 'humidity',    'label': 'HUMI',   'unit': '%',   'fmt': '{:.1f}',
      'color': C['humi'],  'icon': '◆',  'good': (45, 70) },
    { 'key': 'light',       'label': 'LUX',    'unit': 'lux', 'fmt': '{}',
      'color': C['light'], 'icon': '★',  'good': (500, 2500) },
]


# ======================================================================
# Cyberpunk Button with Glitch Effect
# ======================================================================
class CyberButton(tk.Canvas):
    def __init__(self, parent, text='', fg=C['neon_green'], bg=C['card'],
                 hover_bg=C['card_hover'], border_color=C['neon_green'],
                 command=None, font_size=11, width=160, height=40):
        super().__init__(parent, width=width, height=height,
                         bg=C['bg'], highlightthickness=0)
        self._command = command
        self._bg = bg
        self._hover_bg = hover_bg
        self._border_color = border_color
        self._fg = fg
        self._text = text
        self._font = (_MONO, font_size, 'bold')
        self._ww = width
        self._hh = height

        # Outer border (neon glow effect)
        self._border_id = self.create_rectangle(
            1, 1, width-2, height-2,
            outline=border_color, width=2
        )

        # Inner background
        self._bg_id = self.create_rectangle(
            3, 3, width-4, height-4,
            fill=bg, outline=''
        )

        # Corner decorations (cyberpunk style)
        corner_size = 6
        self.create_line(1, 1, 1+corner_size, 1, fill=border_color, width=2)
        self.create_line(1, 1, 1, 1+corner_size, fill=border_color, width=2)
        self.create_line(width-2, 1, width-2-corner_size, 1, fill=border_color, width=2)
        self.create_line(width-2, 1, width-2, 1+corner_size, fill=border_color, width=2)
        self.create_line(1, height-2, 1+corner_size, height-2, fill=border_color, width=2)
        self.create_line(1, height-2, 1, height-2-corner_size, fill=border_color, width=2)
        self.create_line(width-2, height-2, width-2-corner_size, height-2, fill=border_color, width=2)
        self.create_line(width-2, height-2, width-2, height-2-corner_size, fill=border_color, width=2)

        # Text
        self._text_id = self.create_text(
            width//2, height//2,
            text=text, fill=fg,
            font=self._font
        )

        # Event bindings
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

    def set_border(self, color):
        self._border_color = color
        self.itemconfig(self._border_id, outline=color)


# ======================================================================
# Main Application
# ======================================================================
class GreenHouseApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title('GREEN HOUSE // CYBERPUNK EDITION')
        self.root.geometry('1400x900')
        self.root.minsize(1100, 750)
        self.root.configure(bg=C['bg'])

        # Set icon
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.icns')
        try:
            self.root.iconbitmap(default=icon_path)
        except Exception:
            pass

        # Initialize serial handler
        init_handler(port=None)
        self.handler = get_handler()

        # Build UI
        self._build_ui()
        self._refresh_ports()
        self._update_timer()
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    def _build_ui(self):
        root = self.root

        # Main container
        self.mf = tk.Frame(root, bg=C['bg'])
        self.mf.pack(fill='both', expand=True, padx=20, pady=15)

        # Header with glitch effect
        self._build_header(self.mf)

        # Sensor cards
        self._build_cards(self.mf)

        # Control bar
        self._build_controls(self.mf)

        # Charts
        self._build_charts(self.mf)

        # Status bar
        self._build_statusbar(self.mf)

    def _build_header(self, parent):
        # Header container with scanline effect
        header_frame = tk.Frame(parent, bg=C['bg'])
        header_frame.pack(fill='x', pady=(0, 15))

        # Left: Logo and title
        left_frame = tk.Frame(header_frame, bg=C['bg'])
        left_frame.pack(side='left')

        # Logo text with glitch effect
        logo = tk.Label(
            left_frame,
            text='[ GREEN HOUSE ]',
            font=(_MONO, 20, 'bold'),
            bg=C['bg'],
            fg=C['neon_green']
        )
        logo.pack(side='left', padx=(0, 10))

        # Subtitle
        subtitle = tk.Label(
            left_frame,
            text='// CYBERPUNK WASTELAND EDITION',
            font=(_MONO, 9),
            bg=C['bg'],
            fg=C['text_muted']
        )
        subtitle.pack(side='left', padx=(0, 10), pady=(8, 0))

        # Version
        ver = tk.Label(
            left_frame,
            text='v2.0.77',
            font=(_MONO, 8),
            bg=C['bg'],
            fg=C['neon_magenta']
        )
        ver.pack(side='left', padx=(8, 0), pady=(10, 0))

        # Right: Connection status
        right_frame = tk.Frame(header_frame, bg=C['bg'])
        right_frame.pack(side='right')

        # Status indicator
        self._status_canvas = tk.Canvas(
            right_frame, width=12, height=12,
            bg=C['bg'], highlightthickness=0
        )
        self._status_canvas.pack(side='left', padx=(0, 8))
        self._dot_id = self._status_canvas.create_oval(
            2, 2, 10, 10,
            fill=C['neon_orange'], outline=C['neon_orange']
        )

        self.status_label = tk.Label(
            right_frame,
            text='[ CONNECTING... ]',
            font=(_MONO, 10, 'bold'),
            bg=C['bg'],
            fg=C['neon_orange']
        )
        self.status_label.pack(side='left')

        # Decorative line under header
        line_canvas = tk.Canvas(header_frame, height=2, bg=C['bg'], highlightthickness=0)
        line_canvas.pack(fill='x', pady=(8, 0))
        line_canvas.create_line(0, 1, 1400, 1, fill=C['neon_green'], width=1, dash=(4, 2))

    def _build_cards(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 12))

        self._cards = {}
        for cfg in SENSOR_CONFIG:
            card = self._make_card(frame, cfg)
            card['frame'].pack(side='left', fill='both', expand=True, padx=4)
            self._cards[cfg['key']] = card

    def _make_card(self, parent, cfg):
        color = cfg['color']

        # Card container
        outer = tk.Frame(parent, bg=C['bg'], bd=0)

        # Main canvas
        canvas = tk.Canvas(
            outer, width=400, height=150,
            bg=C['card'], highlightthickness=0, bd=0
        )
        canvas.pack(fill='both', expand=True)

        # Border with neon glow
        canvas.create_rectangle(
            2, 2, 398, 148,
            outline=color, width=2
        )

        # Corner accents
        corner = 10
        canvas.create_line(2, 2, 2+corner, 2, fill=color, width=3)
        canvas.create_line(2, 2, 2, 2+corner, fill=color, width=3)
        canvas.create_line(398, 2, 398-corner, 2, fill=color, width=3)
        canvas.create_line(398, 2, 398, 2+corner, fill=color, width=3)
        canvas.create_line(2, 148, 2+corner, 148, fill=color, width=3)
        canvas.create_line(2, 148, 2, 148-corner, fill=color, width=3)
        canvas.create_line(398, 148, 398-corner, 148, fill=color, width=3)
        canvas.create_line(398, 148, 398, 148-corner, fill=color, width=3)

        # Icon (geometric shape)
        canvas.create_text(
            35, 35, text=cfg['icon'],
            font=(_MONO, 24, 'bold'),
            anchor='center', fill=color
        )

        # Label (terminal style)
        canvas.create_text(
            70, 30, text=f'[{cfg["label"]}]',
            font=(_MONO, 11, 'bold'),
            anchor='w', fill=C['text_dim']
        )

        # Large value
        val_id = canvas.create_text(
            30, 85, text='---',
            font=(_MONO, 48, 'bold'),
            anchor='w', fill=C['text']
        )

        # Unit
        unit_id = canvas.create_text(
            240, 95, text=cfg['unit'],
            font=(_MONO, 12),
            anchor='w', fill=C['text_muted']
        )

        # Status indicator
        status_bg = canvas.create_rectangle(
            20, 125, 140, 142,
            fill=color, outline=''
        )
        status_id = canvas.create_text(
            80, 133, text='[ WAITING ]',
            font=(_MONO, 9, 'bold'),
            anchor='center', fill=C['bg']
        )

        return {
            'frame': outer,
            'val_id': val_id,
            'unit_id': unit_id,
            'status_id': status_id,
            'status_bg': status_bg,
            'canvas': canvas,
            'cfg': cfg,
        }

    def _build_controls(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(0, 10))

        # Port selection area
        port_frame = tk.Frame(frame, bg=C['bg'])
        port_frame.pack(side='left', padx=(0, 12))

        # Port label
        port_label = tk.Label(
            port_frame, text='PORT:',
            font=(_MONO, 10, 'bold'),
            bg=C['bg'], fg=C['neon_cyan']
        )
        port_label.pack(side='left', padx=(0, 8))

        # Port dropdown
        self._port_var = tk.StringVar()
        style = ttk.Style()
        style.theme_use('clam')
        style.configure(
            'Cyber.TCombobox',
            fieldbackground=C['card'],
            background=C['card'],
            foreground=C['neon_green'],
            bordercolor=C['neon_green'],
            arrowcolor=C['neon_green']
        )
        self._port_combo = ttk.Combobox(
            port_frame, textvariable=self._port_var,
            font=(_MONO, 10), width=35,
            state='readonly', style='Cyber.TCombobox'
        )
        self._port_combo.pack(side='left', padx=(0, 10))

        # Refresh button
        self._refresh_btn = CyberButton(
            port_frame, text='[ REFRESH ]',
            fg=C['neon_cyan'], bg=C['card'],
            hover_bg=C['card_hover'], border_color=C['neon_cyan'],
            command=self._on_refresh_ports,
            font_size=10, width=100, height=36
        )
        self._refresh_btn.pack(side='left', padx=(0, 8))

        # Connect button
        self._connect_btn = CyberButton(
            port_frame, text='[ CONNECT ]',
            fg=C['neon_green'], bg=C['card'],
            hover_bg=C['card_hover'], border_color=C['neon_green'],
            command=self._on_connect_click,
            font_size=10, width=110, height=36
        )
        self._connect_btn.pack(side='left', padx=(0, 8))

        # Mock mode button
        self._mock_btn = CyberButton(
            port_frame, text='[ SIMULATE ]',
            fg=C['neon_magenta'], bg=C['card'],
            hover_bg=C['card_hover'], border_color=C['neon_magenta'],
            command=self._on_mock_click,
            font_size=10, width=110, height=36
        )
        self._mock_btn.pack(side='left', padx=(8, 0))

        # Right side: Fan + Clear
        right_frame = tk.Frame(frame, bg=C['bg'])
        right_frame.pack(side='right')

        # Fan button
        self.fan_btn = CyberButton(
            right_frame, text='[ FAN: OFF ]',
            fg=C['neon_magenta'], bg=C['card'],
            hover_bg=C['card_hover'], border_color=C['neon_magenta'],
            command=self._toggle_fan,
            font_size=11, width=140, height=38
        )
        self.fan_btn.pack(side='left', padx=(0, 10))

        # Fan status indicator
        self.fan_dot = tk.Canvas(
            right_frame, width=12, height=12,
            bg=C['bg'], highlightthickness=0
        )
        self.fan_dot.pack(side='left', padx=(0, 10))
        self._fd_off = self.fan_dot.create_oval(
            2, 2, 10, 10,
            fill=C['text_muted'], outline=C['text_muted']
        )
        self._fd_on = self.fan_dot.create_oval(
            2, 2, 10, 10,
            fill=C['neon_green'], outline=C['neon_green'],
            state='hidden'
        )

        # Clear button
        self.clear_btn = CyberButton(
            right_frame, text='[ CLEAR ]',
            fg=C['neon_red'], bg=C['card'],
            hover_bg=C['card_hover'], border_color=C['neon_red'],
            command=self._clear_data,
            font_size=10, width=100, height=38
        )
        self.clear_btn.pack(side='left', padx=(10, 0))

    def _build_charts(self, parent):
        container = tk.Frame(parent, bg=C['bg'])
        container.pack(fill='both', expand=True, pady=(0, 8))

        self.figures = {}
        titles = [
            ('[ TEMPERATURE ]', 'temperature', C['temp'], '°C'),
            ('[ HUMIDITY ]', 'humidity', C['humi'], '%'),
            ('[ LUX ]', 'light', C['light'], 'lux'),
        ]

        for title, key, color, unit in titles:
            row = tk.Frame(container, bg=C['bg'])
            row.pack(fill='both', expand=True, pady=2)

            fig = Figure(figsize=(8, 1.5), dpi=100)
            fig.patch.set_facecolor(C['chart_bg'])

            ax = fig.add_subplot(111)
            ax.set_facecolor(C['chart_bg'])

            # Title (terminal style)
            ax.set_title(
                title, color=color, fontsize=9,
                fontfamily=_MONO, fontweight='bold',
                pad=4, loc='left'
            )
            ax.set_ylabel(
                unit, color=C['text_muted'], fontsize=7,
                fontfamily=_MONO, labelpad=2
            )

            # Spines (neon borders)
            ax.spines['top'].set_visible(False)
            ax.spines['right'].set_visible(False)
            ax.spines['left'].set_color(color)
            ax.spines['left'].set_linewidth(1)
            ax.spines['bottom'].set_color(color)
            ax.spines['bottom'].set_linewidth(1)

            ax.tick_params(colors=C['text_muted'], labelsize=6.5)
            ax.grid(True, alpha=0.3, color=C['chart_grid'], linewidth=0.5, linestyle='--')

            # Line
            line, = ax.plot([], [], color=color, linewidth=2,
                            antialiased=True, alpha=0.95)
            ax.fill_between([], [], alpha=0.1, color=color)
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

    def _build_statusbar(self, parent):
        frame = tk.Frame(parent, bg=C['bg'])
        frame.pack(fill='x', pady=(4, 0))

        # Decorative line
        line_canvas = tk.Canvas(frame, height=1, bg=C['bg'], highlightthickness=0)
        line_canvas.pack(fill='x', pady=(0, 4))
        line_canvas.create_line(0, 0, 1400, 0, fill=C['neon_green'], width=1, dash=(2, 2))

        # Status text
        self.time_label = tk.Label(
            frame, text='[ WAITING FOR SENSOR DATA... ]',
            font=(_MONO, 8), bg=C['bg'], fg=C['text_muted']
        )
        self.time_label.pack(side='left')

        self.count_label = tk.Label(
            frame, text='',
            font=(_MONO, 8), bg=C['bg'], fg=C['neon_magenta']
        )
        self.count_label.pack(side='right')

    def _refresh_ports(self):
        """Scan and update serial port dropdown"""
        ports = list_serial_ports()
        if ports:
            self._port_combo['values'] = [f'{p}  ({d})' for p, d in ports]
            self._port_combo.current(0)
        else:
            self._port_combo['values'] = ['[ NO SERIAL DEVICE DETECTED ]']
            self._port_combo.current(0)
            self._port_combo['state'] = 'disabled'

    def _on_refresh_ports(self):
        """Refresh port list button"""
        self._port_combo['state'] = 'readonly'
        self._refresh_ports()

    def _on_connect_click(self):
        """Connect button: switch to selected port"""
        selection = self._port_var.get()
        if not selection or '[ NO SERIAL' in selection:
            return
        # Extract port name
        port = selection.split()[0]
        self.handler.change_port(port)
        self._clear_data()

    def _on_mock_click(self):
        """Switch to Mock simulation mode"""
        self.handler.change_port(None)
        self._clear_data()

    def _toggle_fan(self):
        fan = self.handler.get_fan()
        self.handler.set_fan(not fan)

    def _update_fan_ui(self, on):
        if on:
            self.fan_btn.set_text('[ FAN: ON ]')
            self.fan_btn.set_border(C['neon_green'])
            self.fan_dot.itemconfig(self._fd_on, state='normal')
            self.fan_dot.itemconfig(self._fd_off, state='hidden')
        else:
            self.fan_btn.set_text('[ FAN: OFF ]')
            self.fan_btn.set_border(C['neon_magenta'])
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
            self.status_label.config(text='[ WAITING FOR SENSOR DATA... ]', fg=C['neon_orange'])
            self._status_canvas.itemconfig(self._dot_id, fill=C['neon_orange'], outline=C['neon_orange'])
            return

        # Connection status
        state = self.handler.get_state()
        is_mock = latest.get('_mock', True)

        if state == 'connecting':
            self.status_label.config(text='[ CONNECTING... ]', fg=C['neon_orange'])
            self._status_canvas.itemconfig(self._dot_id, fill=C['neon_orange'], outline=C['neon_orange'])
        elif state == 'connected':
            port = self.handler.get_current_port() or ''
            self.status_label.config(text=f'[ CONNECTED: {port} ]', fg=C['neon_green'])
            self._status_canvas.itemconfig(self._dot_id, fill=C['neon_green'], outline=C['neon_green'])
        elif is_mock:
            self.status_label.config(text='[ SIMULATION MODE ]', fg=C['neon_magenta'])
            self._status_canvas.itemconfig(self._dot_id, fill=C['neon_magenta'], outline=C['neon_magenta'])
        else:
            self.status_label.config(text='[ CONNECTED ]', fg=C['neon_green'])
            self._status_canvas.itemconfig(self._dot_id, fill=C['neon_green'], outline=C['neon_green'])

        # Update cards
        for cfg in SENSOR_CONFIG:
            key = cfg['key']
            card = self._cards[key]
            val = latest.get(key, 0)

            # Large value
            val_text = cfg['fmt'].format(val)
            card['canvas'].itemconfig(card['val_id'], text=val_text)

            # Status text + color
            lo, hi = cfg['good']
            if lo <= val <= hi:
                status_text = '[ NORMAL ]'
                status_color = C['neon_green']
            elif val < lo * 0.8 or val > hi * 1.2:
                status_text = '[ CRITICAL ]'
                status_color = C['neon_red']
            else:
                status_text = '[ WARNING ]'
                status_color = C['neon_yellow']

            card['canvas'].itemconfig(card['status_id'], text=status_text, fill=C['bg'])
            card['canvas'].itemconfig(card['status_bg'], fill=status_color)

        # Fan
        self._update_fan_ui(latest.get('fan_status', False))

        # Timestamp
        ts = latest.get('_timestamp', time.time())
        dt = datetime.fromtimestamp(ts)
        self.time_label.config(text=f'[ LAST UPDATE: {dt.strftime("%H:%M:%S")} ]')
        self.count_label.config(text=f'[ RECORDS: {len(history)} ]')

        # Charts
        if len(history) >= 2:
            indices = list(range(len(history)))

            for cfg in SENSOR_CONFIG:
                key = cfg['key']
                info = self.figures[key]
                vals = [h.get(key, 0) for h in history]

                info['line'].set_data(indices, vals)

                # Update fill
                if info['fill']:
                    info['fill'].remove()
                info['fill'] = info['ax'].fill_between(
                    indices, vals, alpha=0.1, color=cfg['color']
                )

                # Dynamic range
                info['ax'].set_xlim(0, max(len(indices), 60))
                vmin, vmax = min(vals), max(vals)
                margin = max((vmax - vmin) * 0.25, 3)
                info['ax'].set_ylim(vmin - margin, vmax + margin)
                info['canvas'].draw()

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
# Entry Point
# ======================================================================
def main():
    """
    Launch GREEN HOUSE - Cyberpunk Wasteland Edition
    Default: Simulation mode. Select serial port and click [ CONNECT ] to connect hardware.
    """
    try:
        init_handler(port=None)
    except Exception as e:
        print(f'[ ERROR ] Initialization failed: {e}')
        sys.exit(1)

    app = GreenHouseApp()
    app.run()


if __name__ == '__main__':
    main()

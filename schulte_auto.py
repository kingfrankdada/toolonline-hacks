#!/usr/bin/env python3
"""
舒尔特方格速通 v2.0
https://toolonline.net/shult-grid

v2.0:
- 新增期望值模式，使用期望值设定后自动执行
- EMA平滑+增量式比例修正，防止网络与识别波动
- EMA死区设置（默认为0.005），防止过冲震荡
- 点击开销计算修正: server_time - delay×注入次数

python schulte_auto.py
"""

import argparse
import time
import sys
import subprocess
import threading
import re
import math


def ensure_dependencies():
    try:
        import selenium
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("正在安装依赖 selenium 和 webdriver-manager ...")
        pip_candidates = [
            r"C:\Python314\python.exe",
            sys.executable,
        ]
        for py in pip_candidates:
            try:
                subprocess.check_call([py, "-m", "pip", "install", "selenium", "webdriver-manager", "-q"])
                print("依赖安装完成!\n")
                break
            except Exception:
                continue


ensure_dependencies()

import tkinter as tk
from tkinter import ttk
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

SIZE_MAP = {4: "4×4", 5: "5×5", 6: "6×6", 7: "7×7", 8: "8×8", 9: "9×9"}

# 图表配色
COLOR_BG = "#1e1e2e"
COLOR_GRID = "#45475a"
COLOR_TEXT = "#cdd6f4"
COLOR_LINE = "#89b4fa"
COLOR_DOT = "#b4befe"
COLOR_EXPECT = "#f38ba8"
COLOR_DEADBAND = "#a6e3a1"
COLOR_AXIS = "#a6adc8"


class SchulteApp:
    def __init__(self, size=5, delay=0.1, group=4):
        self.size = size
        self.delay = delay
        self.group = group
        self.driver = None

        self._running = False
        self._stop = threading.Event()

        # 期望值模式
        self._expect_running = False
        self._auto_delay = float(delay)
        self._round_num = 0
        self._overheads = []  # 纯点击延迟历史 (server_time - delay)

        # EMA 平滑 + 增量调节参数
        self._ema_overhead = None   # 纯点击开销的 EMA 值，首轮直接初始化
        self._ema_alpha = 0.3      # EMA 平滑系数（越小越平滑，抗噪声越强）
        self._adj_gain = 0.5       # 增量修正比例（越小越保守，防过冲）

        # 收敛图表数据
        self._chart_data = []  # [(round, server_time)]

        self.root = tk.Tk()
        self.root.title("舒尔特方格速通 v2.0")
        self.root.resizable(True, True)
        self.root.attributes("-topmost", True)
        self.root.minsize(650, 750)

        frame = ttk.Frame(self.root, padding=15)
        frame.pack(fill="both", expand=True)
        frame.columnconfigure(0, weight=1)

        ttk.Label(frame, text="舒尔特方格速通 v2.0", font=("", 14, "bold")).grid(
            row=0, column=0, sticky="ew", pady=(0, 10))

        # ---- 设置区 ----
        sf = ttk.LabelFrame(frame, text="设置", padding=8)
        sf.grid(row=1, column=0, sticky="ew", pady=5)

        ttk.Label(sf, text="棋盘阶级:").grid(row=0, column=0, sticky="w", padx=2)
        self.size_var = tk.StringVar(value=str(size))
        ttk.Combobox(sf, textvariable=self.size_var,
                     values=["4", "5", "6", "7", "8", "9"], width=4,
                     state="readonly").grid(row=0, column=1, padx=5)

        ttk.Label(sf, text="点击延迟(秒):").grid(row=0, column=2, sticky="w", padx=2)
        self.delay_var = tk.StringVar(value=str(delay))
        self.delay_entry = ttk.Entry(sf, textvariable=self.delay_var, width=8)
        self.delay_entry.grid(row=0, column=3, padx=5)

        ttk.Label(sf, text="同步连点数:").grid(row=1, column=0, sticky="w", padx=2)
        self.group_var = tk.StringVar(value=str(group))
        self.group_entry = ttk.Entry(sf, textvariable=self.group_var, width=8)
        self.group_entry.grid(row=1, column=1, padx=5)

        self.auto_retry_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="自动重试", variable=self.auto_retry_var).grid(
            row=1, column=2, columnspan=2, sticky="w", padx=2)

        ttk.Separator(sf, orient="horizontal").grid(row=2, column=0, columnspan=4, sticky="ew", pady=4)

        # ---- 期望值设置 ----
        self.use_expect_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="使用期望值",
                        variable=self.use_expect_var,
                        command=self._on_expect_toggle).grid(row=3, column=0, sticky="w", padx=2)

        ttk.Label(sf, text="期望时间:").grid(row=3, column=1, sticky="e", padx=2)
        self.expect_time_var = tk.StringVar(value="5.000")
        self.expect_entry = ttk.Entry(sf, textvariable=self.expect_time_var, width=8, state="disabled")
        self.expect_entry.grid(row=3, column=2, padx=2)
        ttk.Label(sf, text="秒").grid(row=3, column=3, sticky="w")

        ttk.Label(sf, text="死区(±秒):").grid(row=4, column=0, sticky="w", padx=2)
        self.deadband_var = tk.StringVar(value="0.005")
        self.deadband_entry = ttk.Entry(sf, textvariable=self.deadband_var, width=8)
        self.deadband_entry.grid(row=4, column=1, padx=5)

        self.auto_info_var = tk.StringVar(value="")
        ttk.Label(sf, textvariable=self.auto_info_var, foreground="blue").grid(
            row=5, column=0, columnspan=4, sticky="w", padx=2)

        # ---- 状态 ----
        ttk.Separator(frame, orient="horizontal").grid(row=2, column=0, sticky="ew", pady=8)

        self.status_var = tk.StringVar(value="正在启动浏览器...")
        ttk.Label(frame, textvariable=self.status_var).grid(
            row=3, column=0, sticky="ew", pady=5)

        # ---- 按钮 ----
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, sticky="ew", pady=(10, 5))
        self.start_btn = ttk.Button(btn_frame, text="开始", command=self.on_start, state="disabled", width=10)
        self.start_btn.pack(side="left", padx=5)
        self.restart_btn = ttk.Button(btn_frame, text="重新开始", command=self.on_restart, state="disabled", width=10)
        self.restart_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.on_stop, state="disabled", width=10)
        self.stop_btn.pack(side="left", padx=5)
        self.clear_btn = ttk.Button(btn_frame, text="清空数据", command=self.on_clear_data, width=10)
        self.clear_btn.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(frame, mode="determinate")
        self.progress.grid(row=5, column=0, sticky="ew", pady=5)

        # ---- 结果 ----
        self.result_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.result_var).grid(
            row=6, column=0, sticky="ew", pady=2)

        # ---- 历史记录 ----
        hist_frame = ttk.LabelFrame(frame, text="服务器时间记录", padding=8)
        hist_frame.grid(row=7, column=0, sticky="nsew", pady=5)

        # 表头行（固定在顶部，不参与滚动）
        self.hist_header = ttk.Frame(hist_frame)
        self.hist_header.pack(fill="x", side="top")

        _headers = ["轮次", "服务器(秒)", "纯点击(秒)", "点击延迟(秒)", "连点数", "调整"]
        for i, h in enumerate(_headers):
            ttk.Label(self.hist_header, text=h, anchor="center",
                      font=("", 9, "bold"), relief="groove", padding=2
            ).grid(row=0, column=i, padx=0, pady=(0, 2), sticky="nsew")

        for c in range(6):
            self.hist_header.columnconfigure(c, weight=1, uniform="col")

        # 滚动区域：Canvas + 内部Frame（仅数据行）
        scroll_container = ttk.Frame(hist_frame)
        scroll_container.pack(fill="both", expand=True, side="top")

        self.hist_canvas = tk.Canvas(scroll_container, height=150, highlightthickness=0)
        self.hist_sb = ttk.Scrollbar(scroll_container, orient="vertical", command=self.hist_canvas.yview)
        self.hist_inner = ttk.Frame(self.hist_canvas)

        self.hist_inner.bind("<Configure>",
            lambda e: self.hist_canvas.configure(scrollregion=self.hist_canvas.bbox("all")))
        self._hist_canvas_win = self.hist_canvas.create_window((0, 0), window=self.hist_inner, anchor="nw")
        self.hist_canvas.configure(yscrollcommand=self.hist_sb.set)

        # Canvas 宽度跟随父容器
        self.hist_canvas.bind("<Configure>",
            lambda e: self.hist_canvas.itemconfig(self._hist_canvas_win, width=e.width))

        self.hist_canvas.pack(side="left", fill="both", expand=True)
        self.hist_sb.pack(side="right", fill="y")

        # 鼠标滚轮滚动
        def _on_hist_enter(e):
            self.hist_canvas.bind_all("<MouseWheel>",
                lambda ev: self.hist_canvas.yview_scroll(int(-1 * (ev.delta / 120)), "units"))
        def _on_hist_leave(e):
            self.hist_canvas.unbind_all("<MouseWheel>")
        self.hist_canvas.bind("<Enter>", _on_hist_enter)
        self.hist_canvas.bind("<Leave>", _on_hist_leave)

        # 列权重：让列随容器宽度自适应均分
        for c in range(6):
            self.hist_inner.columnconfigure(c, weight=1, uniform="col")

        self._hist_row = 0

        # ---- 收敛图表（下方） ----
        chart_frame = ttk.LabelFrame(frame, text="逼近期望值", padding=4)
        chart_frame.grid(row=8, column=0, sticky="nsew", pady=5)

        self.chart_canvas = tk.Canvas(chart_frame, width=600, height=250,
                                     bg=COLOR_BG, highlightthickness=0)
        self.chart_canvas.pack(fill="both", expand=True)

        # 允许行7和行8垂直扩展（历史记录 + 图表）
        frame.rowconfigure(7, weight=1)
        frame.rowconfigure(8, weight=1)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------ helpers
    def _current_delay(self):
        """获取当前应使用的点击延迟：期望模式用自动调整值，否则用输入框值"""
        if self.use_expect_var.get():
            return self._auto_delay
        try:
            return float(self.delay_var.get())
        except ValueError:
            return 0.1

    def _current_group(self):
        """获取当前应使用的连点数：期望模式用阶数²-1，否则用输入框值"""
        if self.use_expect_var.get():
            size = int(self.size_var.get())
            return size * size - 1
        try:
            return int(self.group_var.get())
        except ValueError:
            return 4

    # ------------------------------------------------------------------ log
    def log(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    # ----------------------------------------------------------- history tree
    def _add_history(self, round_num, server_time, click_delay, group_delay, group, adjust=""):
        """线程安全地添加一条历史记录，调整列中只有箭头染色"""
        self._hist_row += 1
        # 数据行从0开始（表头已移到 hist_canvas 外），每行占2行 (数据+分隔线)
        row = (self._hist_row - 1) * 2  # row 0, 2, 4...

        vals = [str(round_num), f"{server_time:.3f}", f"{click_delay:.3f}",
                f"{group_delay:.3f}", str(group)]
        for i, v in enumerate(vals):
            ttk.Label(self.hist_inner, text=v, anchor="center",
                      padding=2
            ).grid(row=row, column=i, sticky="nsew")

        # 调整列：只有箭头染色
        adj_frame = tk.Frame(self.hist_inner)
        adj_frame.grid(row=row, column=5, sticky="nsew")

        if adjust:
            m = re.match(r'([\d.]+)\(([▲▼±])([^)]+)\)', adjust)
            if m:
                prefix, arrow, suffix = m.groups()
                tk.Label(adj_frame, text=prefix + "(", font=("", 9)).pack(side="left")
                color = "#e74c3c" if arrow == "▲" else "#2ecc71" if arrow == "▼" else "gray"
                tk.Label(adj_frame, text=arrow, fg=color, font=("", 9, "bold")).pack(side="left")
                tk.Label(adj_frame, text=suffix + ")", font=("", 9)).pack(side="left")
            else:
                ttk.Label(adj_frame, text=adjust, anchor="center").pack(side="left")
        else:
            ttk.Label(adj_frame, text="", anchor="center").pack(side="left")

        # 行间分割线（放在数据行下方的偶数行）
        sep_row = row + 1
        ttk.Separator(self.hist_inner, orient="horizontal").grid(
            row=sep_row, column=0, columnspan=6, sticky="ew", padx=2)

        # 滚动到底部
        self.hist_canvas.update_idletasks()
        self.hist_canvas.yview_moveto(1.0)

        # 收敛图表数据
        self._chart_data.append((round_num, server_time))
        self.root.after(0, self._draw_chart)

    # ========================================================= 收敛图表
    def _draw_chart(self):
        """绘制收敛图表：纵轴=实际时间，横轴=次数，期望值参考线"""
        c = self.chart_canvas
        c.delete("all")

        w = c.winfo_width()
        h = c.winfo_height()
        if w < 100 or h < 80:
            w, h = 600, 250

        pad_l, pad_r, pad_t, pad_b = 55, 55, 18, 30
        chart_w = w - pad_l - pad_r
        chart_h = h - pad_t - pad_b

        # 期望时间（3位小数）
        try:
            expected = float(self.expect_time_var.get())
        except (ValueError, tk.TclError):
            expected = 5.000

        data = self._chart_data
        if not data:
            c.create_text(w // 2, h // 2, text="等待数据...", fill=COLOR_TEXT, font=("", 12))
            return

        times = [d[1] for d in data]
        # y 范围：以期望值为锚点，扩展到包含所有数据
        try:
            deadband = float(self.deadband_var.get())
        except (ValueError, tk.TclError):
            deadband = 0.005
        all_vals = times + [expected]
        y_min = min(all_vals) * 0.85
        y_max = max(all_vals) * 1.15
        if y_max - y_min < 0.5:
            y_min = expected - 0.25
            y_max = expected + 0.25
        y_range = y_max - y_min

        n_points = len(data)
        x_max = max(n_points + 1, 5)

        # 背景矩形
        c.create_rectangle(pad_l, pad_t, w - pad_r, h - pad_b,
                           fill=COLOR_BG, outline=COLOR_GRID)

        # ---- 网格线和Y轴标签 ----
        num_grid = 6
        for i in range(num_grid + 1):
            frac = i / num_grid
            y = pad_t + chart_h * (1 - frac)
            val = y_min + y_range * frac
            c.create_line(pad_l, y, w - pad_r, y, fill=COLOR_GRID, dash=(2, 4))
            c.create_text(pad_l - 4, y, text=f"{val:.3f}", anchor="e",
                          fill=COLOR_AXIS, font=("", 8))

        # ---- 期望值参考线 ----
        y_exp = pad_t + chart_h * (1 - (expected - y_min) / y_range)
        c.create_line(pad_l, y_exp, w - pad_r, y_exp, fill=COLOR_EXPECT, width=2, dash=(8, 4))
        c.create_text(pad_l + 5, y_exp - 10, text=f"期望 {expected:.3f}s",
                      anchor="w", fill=COLOR_EXPECT, font=("", 9, "bold"))

        # ---- 死区标注（右侧纵轴绿色数字，标注在期望值高度） ----
        c.create_text(w - pad_r + 4, y_exp, text=f"±{deadband:.3f}", anchor="w",
                      fill=COLOR_DEADBAND, font=("", 8))

        # ---- 数据折线 ----
        points_xy = []
        for i, (rnd, st) in enumerate(data):
            x = pad_l + chart_w * (i + 1) / x_max
            y = pad_t + chart_h * (1 - (st - y_min) / y_range)
            points_xy.append((x, y))

        # 填充区域（折线到期望线之间）
        if len(points_xy) >= 2:
            fill_coords = [points_xy[0][0], y_exp]
            for x, y in points_xy:
                fill_coords.extend([x, y])
            fill_coords.extend([points_xy[-1][0], y_exp])
            c.create_polygon(fill_coords, fill="#313244", outline="", stipple="gray25")

        # 连线
        if len(points_xy) >= 2:
            flat_coords = []
            for x, y in points_xy:
                flat_coords.extend([x, y])
            c.create_line(flat_coords, fill=COLOR_LINE, width=2.5, smooth=True)

        # 数据点：只有最后一个画圆点
        for i, (x, y) in enumerate(points_xy):
            if i == len(points_xy) - 1:
                r = 5
                c.create_oval(x - r, y - r, x + r, y + r, fill=COLOR_DOT, outline=COLOR_LINE, width=1)
                c.create_text(x, y - 12, text=f"{data[-1][1]:.3f}",
                              fill=COLOR_TEXT, font=("", 9, "bold"))

        # X 轴标签
        c.create_text(pad_l + chart_w // 2, h - 5, text="次数", fill=COLOR_TEXT, font=("", 9))
        step = max(1, n_points // 8)
        for i in range(0, n_points, step):
            x = pad_l + chart_w * (i + 1) / x_max
            rnd = data[i][0]
            c.create_text(x, h - pad_b + 12, text=str(rnd), fill=COLOR_AXIS, font=("", 8))
            c.create_line(x, h - pad_b, x, h - pad_b + 4, fill=COLOR_AXIS)

        # 最后一个点也标
        if n_points > 1 and (n_points - 1) % step != 0:
            x = pad_l + chart_w * n_points / x_max
            c.create_text(x, h - pad_b + 12, text=str(data[-1][0]),
                          fill=COLOR_AXIS, font=("", 8))
            c.create_line(x, h - pad_b, x, h - pad_b + 4, fill=COLOR_AXIS)

        # Y 轴标题
        c.create_text(12, pad_t + chart_h // 2, text="实际时间(秒)",
                      fill=COLOR_TEXT, font=("", 9), angle=90)

    # -------------------------------------------------------- expect toggle
    def _on_expect_toggle(self):
        if self.use_expect_var.get():
            self.expect_entry.config(state="normal")
            self.delay_entry.config(state="disabled")
            self.group_entry.config(state="disabled")
            self.auto_retry_var.set(True)  # 期望值模式自动勾选自动重试
            size = int(self.size_var.get())
            auto_group = size * size - 1
            self.group_var.set(str(auto_group))
            # 初始化 _auto_delay 为当前输入框的值
            try:
                self._auto_delay = float(self.delay_var.get())
            except ValueError:
                self._auto_delay = 0.5
            self.auto_info_var.set(f"连点数={auto_group} (阶数²-1), 延迟={self._auto_delay:.3f}s, EMA α={self._ema_alpha}, 死区±{self.deadband_var.get()}s, 按[开始]启动")
        else:
            self.expect_entry.config(state="disabled")
            self.delay_entry.config(state="normal")
            self.group_entry.config(state="normal")
            self.auto_info_var.set("")

    # ======================================================= expect mode
    def _start_expect_mode(self):
        """启动期望值自动模式"""
        self._stop.clear()
        self._expect_running = True
        size = int(self.size_var.get())
        self._auto_delay = float(self.delay_var.get() or "0.5")
        self.group = size * size - 1
        self.group_var.set(str(self.group))

        self.start_btn.config(state="disabled")
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        thread = threading.Thread(target=self._expect_loop, daemon=True)
        thread.start()

    def _expect_loop(self):
        """期望值模式: 连续运行 → 记录服务器时间 → 自动调整延迟 → 重来"""
        size = int(self.size_var.get())
        group = size * size - 1
        first_round = True

        while self._expect_running and not self._stop.is_set():
            self._round_num += 1
            delay = self._auto_delay

            self.log(f"期望值模式: 第{self._round_num}轮, 连点={group}, 点击延迟={delay:.3f}s")

            # 选方格大小（仅首次或切换时）
            if first_round and size != 5:
                self._select_grid_size(size)
            first_round = False

            # 点开始 / 重新开始
            if self._round_num == 1:
                self.log(f"第{self._round_num}轮: 点击开始游戏...")
            else:
                self._dismiss_modal()
                time.sleep(0.2)
                self.log(f"第{self._round_num}轮: 点击重新开始...")

            if self._stop.is_set():
                break

            if not self._click_start_button():
                self.root.after(0, lambda: self.log("未找到开始按钮，停止期望值模式"))
                break

            if self._stop.is_set():
                break
            time.sleep(0.15)

            # 执行连点
            ok = self._do_click(delay, group)
            if not ok:
                break

            if self._stop.is_set():
                break

            # 捕获服务器时间
            time.sleep(0.5)
            server_time = self._capture_server_time()

            if server_time is not None:
                # 计算总注入延迟: 注入次数 × 每次延迟
                max_num = size * size
                delay_count = max(1, (max_num - 1) // group)
                total_injected = delay * delay_count
                click_delay = server_time - total_injected  # 纯点击开销（含网络波动）
                self._overheads.append(click_delay)
                adjust = self._auto_adjust_delay(size, server_time=server_time)
                rn = self._round_num
                self.root.after(0, lambda rn=rn, st=server_time, cd=click_delay, d=delay, g=group, a=adjust:
                    self._add_history(rn, st, cd, d, g, a))
                self.root.after(0, lambda rn=rn, st=server_time:
                    self.result_var.set(f"第{rn}轮: 服务器 {st:.3f}s"))

                # 达到期望值（等于目标，容许浮点精度误差）自动停止
                try:
                    target = float(self.expect_time_var.get())
                except (ValueError, tk.TclError):
                    target = None
                if target is not None and abs(server_time - target) < 0.0001:
                    self.root.after(0, lambda t=target, s=server_time:
                        self.result_var.set(f"✓ 达到期望值! 目标={t:.3f}s 实际={s:.3f}s"))
                    self.log(f"达到期望值 {target:.3f}s，实际 {server_time:.3f}s，自动停止")
                    break
            else:
                self.log("未捕获到服务器时间")

            if not self._expect_running or self._stop.is_set():
                break

            # 短暂等待后启动下一轮
            self.log("1秒后开始下一轮...")
            for _ in range(10):
                if self._stop.is_set() or not self._expect_running:
                    break
                time.sleep(0.1)

        self._expect_running = False
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))
        self.log("期望值模式已停止")

    def _auto_adjust_delay(self, size, server_time=None):
        """EMA 平滑 + 增量式比例调节，逼近期望时间

        算法:
        1. 计算本轮纯点击开销 = server_time - 总注入延迟
        2. 用 EMA 平滑纯点击开销（alpha=0.3，抗周期性噪声）
        3. 理想延迟 = (期望时间 - EMA开销) / 注入延迟次数
        4. 增量修正: 新延迟 = 当前延迟 + K × (理想延迟 - 当前延迟)
           K=0.5 表示每轮只走差距的一半，防止过冲震荡
        5. 死区: 实际服务器时间在 期望值±死区 内时，锁定延迟不变

        返回调整文本，如 "0.150(▲+0.050)" 或 "0.080(▼-0.020)"
        """
        if not self._overheads:
            return ""

        try:
            target_time = float(self.expect_time_var.get())
        except ValueError:
            target_time = 5.000

        # --- 第1步: 纯点击开销 ---
        # 本轮开销 = 服务器时间 - 注入的总延迟
        # 对于 group=N 的连点: 注入次数 = floor(max_num / N), 但之前已用 overheads 存了 server_time - delay
        # 这里用 ema 跨轮平滑，overheads 里最后一条就是本轮开销
        this_overhead = self._overheads[-1]

        # --- 第2步: EMA 平滑 ---
        if self._ema_overhead is None:
            self._ema_overhead = this_overhead  # 首轮直接初始化
        else:
            a = self._ema_alpha
            self._ema_overhead = a * this_overhead + (1 - a) * self._ema_overhead

        # --- 第3步: 计算理想注入延迟 ---
        # 总时间 = EMA开销 + 注入延迟次数 × 每次延迟
        # 注入延迟次数: 对于 size×size 方格, group=N, 注入次数 = ceil(max_num/N) - 1
        # 简化: 总数 group=size²-1 时, max_num=size², 注入次数 = size²//(size²-1) = 1 (仅在末尾不注入)
        # 实际: max_num // group 次 (最后一个整组不注入)
        max_num = size * size
        group = size * size - 1
        delay_count = max(1, (max_num - 1) // group)  # 注入延迟的次数
        ideal_delay = (target_time - self._ema_overhead) / delay_count
        ideal_delay = max(0.01, ideal_delay)  # 最低 0.01s

        # --- 死区检测: 实际服务器时间在 target ± deadband 内则不调整 ---
        try:
            deadband = float(self.deadband_var.get())
        except (ValueError, tk.TclError):
            deadband = 0.005

        if server_time is not None and abs(server_time - target_time) <= deadband:
            # 死区内：EMA 仍然更新（跟踪噪声），但延迟锁定不变
            adjust_text = f"{self._auto_delay:.3f}(±{deadband:.3f})"
            self.root.after(0, lambda nd=self._auto_delay: self.delay_var.set(f"{nd:.3f}"))
            self.root.after(0, lambda: self.auto_info_var.set(
                f"延迟={self._auto_delay:.3f}s(死区锁), 目标={target_time:.3f}s, "
                f"EMA α={self._ema_alpha}, 开销={self._ema_overhead:.3f}s, 注入×{delay_count}"))
            return adjust_text

        # --- 第4步: 增量修正 ---
        old_delay = self._auto_delay
        new_delay = old_delay + self._adj_gain * (ideal_delay - old_delay)
        new_delay = max(0.01, new_delay)
        self._auto_delay = new_delay

        # 调整方向反馈
        diff = new_delay - old_delay
        abs_diff = abs(diff)
        if abs_diff < 0.001:
            adjust_text = f"{new_delay:.3f}(±0)"
        elif diff < 0:
            adjust_text = f"{new_delay:.3f}(▼-{abs_diff:.3f})"
        else:
            adjust_text = f"{new_delay:.3f}(▲+{abs_diff:.3f})"

        # 同步更新延迟输入框供显示
        self.root.after(0, lambda nd=new_delay: self.delay_var.set(f"{nd:.3f}"))

        self.root.after(0, lambda: self.auto_info_var.set(
            f"延迟={new_delay:.3f}s, 目标={target_time:.3f}s, "
            f"EMA α={self._ema_alpha}, 开销={self._ema_overhead:.3f}s, 注入×{delay_count}"))

        return adjust_text

    # ============================================ server time capture
    def _capture_server_time(self):
        """读取页面中服务器返回的完成时间 (全部点击完成，用时xx秒)，精确到3位小数"""
        for _ in range(10):
            if self._stop.is_set():
                return None
            try:
                elements = self.driver.find_elements(By.XPATH,
                    "//*[contains(text(),'用时')]")
                for el in elements:
                    try:
                        if not el.is_displayed():
                            continue
                    except Exception:
                        continue
                    text = el.text.strip()
                    match = re.search(r'(\d+\.?\d*)\s*秒', text)
                    if match:
                        return float(match.group(1))

                elements2 = self.driver.find_elements(By.XPATH,
                    "//*[contains(text(),'秒')]")
                for el in elements2:
                    try:
                        if not el.is_displayed():
                            continue
                    except Exception:
                        continue
                    text = el.text.strip()
                    match = re.search(r'(\d+\.?\d*)\s*秒', text)
                    if match:
                        return float(match.group(1))

                for sel in [".el-message-box__message", ".el-notification__content",
                            ".el-message__content", ".result-text", ".game-result",
                            "[class*='result']", "[class*='time']"]:
                    try:
                        els = self.driver.find_elements(By.CSS_SELECTOR, sel)
                        for el in els:
                            try:
                                if not el.is_displayed():
                                    continue
                            except Exception:
                                continue
                            text = el.text.strip()
                            match = re.search(r'(\d+\.?\d*)\s*秒', text)
                            if match:
                                return float(match.group(1))
                    except Exception:
                        continue
            except Exception:
                pass
            time.sleep(0.2)
        return None

    # ============================================ existing methods
    def on_clear_data(self):
        """清空历史记录和图表数据"""
        # 删除所有数据行和分隔线
        for widget in self.hist_inner.winfo_children():
            widget.destroy()
        self._hist_row = 0
        # 滚动回顶部
        self.hist_canvas.update_idletasks()
        self.hist_canvas.yview_moveto(0.0)
        # 清空图表数据
        self._chart_data.clear()
        self._overheads.clear()
        self._ema_overhead = None  # 重置 EMA
        self._round_num = 0
        # 重绘空图表
        self._draw_chart()
        # 清空标签
        self.auto_info_var.set("")
        self.result_var.set("")
        self.log("数据已清空")

    def on_close(self):
        self._stop.set()
        self._expect_running = False
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.root.destroy()

    def on_stop(self):
        """停止当前执行（包括期望值模式）"""
        self._stop.set()
        self._expect_running = False
        self.log("正在停止...")
        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))

    def launch_browser(self):
        try:
            options = Options()
            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            self.driver.get("https://toolonline.net/shult-grid")

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".game-area-mode"))
            )

            self.log("浏览器就绪，设置参数后点击 [开始]")
            self.start_btn.config(state="normal")

        except Exception as e:
            self.log(f"启动失败: {e}")
            self.start_btn.config(state="disabled")

    def _select_grid_size(self, size):
        if size == 5:
            return True
        size_text = SIZE_MAP.get(size)
        if not size_text:
            return False
        trigger = self.driver.find_element(By.CSS_SELECTOR, ".level-group")
        trigger.click()
        time.sleep(0.5)
        items = self.driver.find_elements(By.CSS_SELECTOR, ".el-dropdown-menu__item")
        for item in items:
            if item.text.strip() == size_text:
                item.click()
                time.sleep(0.3)
                return

    def on_start(self):
        self._stop.clear()
        self.start_btn.config(state="disabled")
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_var.set("")
        # 期望模式：直接进入期望循环
        if self.use_expect_var.get():
            self._start_expect_mode()
            return
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def on_restart(self):
        """重新开始"""
        self._stop.clear()
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_var.set("")
        # 期望模式：进入期望循环
        if self.use_expect_var.get():
            self._start_expect_mode()
            return
        thread = threading.Thread(target=self._restart, daemon=True)
        thread.start()

    def _click_start_button(self):
        """点击页面的'开始游戏'或'重新开始'按钮"""
        for text in ["重新开始", "开始游戏", "再来一次", "再试一次"]:
            try:
                buttons = self.driver.find_elements(By.XPATH, f"//button[contains(.,'{text}')]")
                for btn in buttons:
                    if btn.is_displayed():
                        btn.click()
                        return True
            except Exception:
                pass
        return False

    def _dismiss_modal(self):
        """尝试关闭结果弹窗"""
        try:
            overlays = self.driver.find_elements(By.CSS_SELECTOR,
                ".el-overlay, .el-dialog__wrapper, .modal-backdrop")
            for overlay in overlays:
                if overlay.is_displayed():
                    close_btns = overlay.find_elements(By.CSS_SELECTOR,
                        ".el-button--primary, .el-dialog__close")
                    for btn in close_btns:
                        if btn.is_displayed():
                            btn.click()
                            time.sleep(0.3)
                            return
                    overlay.click()
                    time.sleep(0.3)
                    return
        except Exception:
            pass

    def _click_cell(self, cell):
        """点击一个格子，优先WebElement.click，失败则JS点击"""
        try:
            cell.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", cell)

    # ============================================ _run / _restart (normal mode)
    def _run(self):
        """首次启动 — 普通模式"""
        size = int(self.size_var.get())
        delay = self._current_delay()
        group = self._current_group()

        if size != 5:
            self.log(f"切换到 {size}x{size}...")
            self._select_grid_size(size)

        self.log("点击开始游戏...")
        if not self._click_start_button():
            self.root.after(0, lambda: self.log("未找到开始游戏按钮"))
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return

        time.sleep(0.15)
        self._round_num += 1
        self._do_click_and_record(delay, group, auto_adjust=self.use_expect_var.get())

        if self.auto_retry_var.get() and not self._stop.is_set():
            current_delay = self._current_delay()
            current_group = self._current_group()
            self._auto_retry_loop(current_delay, current_group)

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _restart(self):
        """重新开始 — 普通模式"""
        delay = self._current_delay()
        group = self._current_group()

        try:
            self._dismiss_modal()
            time.sleep(0.2)

            self.log("点击重新开始...")
            if not self._click_start_button():
                self.root.after(0, lambda: self.log("未找到重新开始按钮"))
                self.root.after(0, lambda: self.restart_btn.config(state="normal"))
                return

            time.sleep(0.15)
            self._round_num += 1
            self._do_click_and_record(delay, group, auto_adjust=self.use_expect_var.get())

            if self.auto_retry_var.get() and not self._stop.is_set():
                current_delay = self._current_delay()
                current_group = self._current_group()
                self._auto_retry_loop(current_delay, current_group)

        except Exception as e:
            self.root.after(0, lambda: self.log(f"出错: {e}"))

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _auto_retry_loop(self, delay, group):
        """自动重试循环 — 每轮自动读取最新 delay/group"""
        while self.auto_retry_var.get() and not self._stop.is_set():
            self.log("自动重试: 等待1秒...")
            for _ in range(10):
                if self._stop.is_set():
                    return
                time.sleep(0.1)

            try:
                self._dismiss_modal()
                time.sleep(0.2)

                if self._stop.is_set():
                    return

                self.log("自动重试: 点击重新开始...")
                if not self._click_start_button():
                    self.root.after(0, lambda: self.log("自动重试: 未找到重新开始按钮，停止"))
                    return

                time.sleep(0.15)
                # 每轮重新读取最新延迟/连点数（可能被自动调整过）
                delay = self._current_delay()
                group = self._current_group()
                self._round_num += 1
                ok = self._do_click_and_record(delay, group, auto_adjust=self.use_expect_var.get())
                if not ok:
                    return
            except Exception as e:
                self.root.after(0, lambda: self.log(f"自动重试出错: {e}"))
                return

    def _do_click_and_record(self, delay, group, auto_adjust=False):
        """执行连点 + 记录服务器时间 + 可选自动调整延迟"""
        ok = self._do_click(delay, group)
        if ok:
            time.sleep(0.5)
            server_time = self._capture_server_time()
            if server_time is not None:
                # 计算总注入延迟: 注入次数 × 每次延迟
                size = int(self.size_var.get())
                max_num = size * size
                delay_count = max(1, (max_num - 1) // group)
                total_injected = delay * delay_count
                click_delay = server_time - total_injected  # 纯点击开销
                # 自动调整延迟（当期望模式开启时）
                adjust = ""
                if auto_adjust:
                    self._overheads.append(click_delay)
                    adjust = self._auto_adjust_delay(size, server_time=server_time)
                rn = self._round_num
                self.root.after(0, lambda rn=rn, st=server_time, cd=click_delay, d=delay, g=group, a=adjust:
                    self._add_history(rn, st, cd, d, g, a))
                self.root.after(0, lambda rn=rn, st=server_time, d=delay:
                    self.result_var.set(f"第{rn}轮: 服务器 {st:.3f}s, 点击延迟 {d:.3f}s"))
            else:
                rn = self._round_num
                self.root.after(0, lambda rn=rn: self.log(f"第{rn}轮: 未捕获到服务器时间"))
        return ok

    # ============================================ core click logic
    def _do_click(self, delay, group):
        """读取方格并执行连点"""
        try:
            all_items = self.driver.find_elements(By.CSS_SELECTOR, ".game-area-mode div.item")

            cells = {}
            for item in all_items:
                text = item.text.strip()
                if text.isdigit():
                    cells[int(text)] = item

            if not cells:
                time.sleep(0.05)
                for item in all_items:
                    text = item.text.strip()
                    if text.isdigit():
                        cells[int(text)] = item

            if not cells:
                self.root.after(0, lambda: self.log("未识别到方格数字"))
                self.root.after(0, lambda: self.start_btn.config(state="normal"))
                self.root.after(0, lambda: self.restart_btn.config(state="normal"))
                return False

            max_num = max(cells.keys())
            self.root.after(0, lambda: self.log(f"{len(cells)}格, 连点{group}, 1-{max_num}..."))
            self.root.after(0, lambda: self.progress.config(maximum=max_num, value=0))

            start_time = time.time()

            for i in range(1, max_num + 1):
                if self._stop.is_set():
                    self.root.after(0, lambda: self.log("已停止"))
                    return False

                if i not in cells:
                    continue

                self._click_cell(cells[i])
                self.root.after(0, lambda n=i: self._update_progress(n, max_num))

                if i % group == 0 and i < max_num:
                    time.sleep(delay)

            elapsed = time.time() - start_time
            self.root.after(0, lambda: self.log(f"完成! 用时 {elapsed:.3f} 秒"))
            self.root.after(0, lambda: self.result_var.set(
                f"用时: {elapsed:.3f}s, 连点{group}, 点击延迟{delay:.3f}s"))
            return True

        except Exception as e:
            self.root.after(0, lambda: self.log(f"出错: {e}"))
            return False

    def _update_progress(self, num, max_num):
        self.progress["maximum"] = max_num
        self.progress["value"] = num
        self.log(f"点击: {num}/{max_num}")

    # ============================================ run
    def run(self):
        t = threading.Thread(target=self.launch_browser, daemon=True)
        t.start()
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="舒尔特方格速通 v2.0")
    parser.add_argument("--size", type=int, default=5, choices=[4, 5, 6, 7, 8, 9],
                        help="方格大小 (默认5, 即5x5)")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="每组点击之间的点击延迟秒数 (默认0.1)")
    parser.add_argument("--group", type=int, default=4,
                        help="每组连点数量 (默认4, 1=逐个点击)")
    args = parser.parse_args()

    app = SchulteApp(size=args.size, delay=args.delay, group=args.group)
    app.run()


if __name__ == "__main__":
    main()

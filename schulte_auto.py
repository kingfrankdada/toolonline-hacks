#!/usr/bin/env python3
"""
舒尔特方格速通 v1.0
https://toolonline.net/shult-grid

使用独立双线程：
dom识别线程负责对棋盘内元素进行识别并且规划路径
点击线程负责同步执行点击操作
使用dom元素预规划处理，缩小开始游戏后点击的延迟

python schulte_auto.py
"""

import argparse
import time
import sys
import subprocess
import threading

def ensure_dependencies():
    try:
        import selenium
        from webdriver_manager.chrome import ChromeDriverManager
    except ImportError:
        print("正在安装依赖 selenium 和 webdriver-manager ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "selenium", "webdriver-manager", "-q"])
        print("依赖安装完成!\n")

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


SIZE_MAP = {4: "4\u00d74", 5: "5\u00d75", 6: "6\u00d76", 7: "7\u00d77", 8: "8\u00d78", 9: "9\u00d79"}


class SchulteApp:
    def __init__(self, size=5, delay=0.1, group=4):
        self.size = size
        self.delay = delay
        self.group = group
        self.driver = None

        self._running = False
        self._stop = threading.Event()

        self.root = tk.Tk()
        self.root.title("舒尔特方格速通 v1.0")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        frame = ttk.Frame(self.root, padding=20)
        frame.pack()

        ttk.Label(frame, text="舒尔特方格速通 v1.0", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(0, 10))

        # 设置区
        sf = ttk.LabelFrame(frame, text="设置", padding=8)
        sf.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

        ttk.Label(sf, text="棋盘阶级:").grid(row=0, column=0, sticky="w", padx=2)
        self.size_var = tk.StringVar(value=str(size))
        ttk.Combobox(sf, textvariable=self.size_var,
                     values=["4", "5", "6", "7", "8", "9"], width=4,
                     state="readonly").grid(row=0, column=1, padx=5)

        ttk.Label(sf, text="间隔(秒):").grid(row=0, column=2, sticky="w", padx=2)
        self.delay_var = tk.StringVar(value=str(delay))
        ttk.Entry(sf, textvariable=self.delay_var, width=6).grid(row=0, column=3, padx=5)

        ttk.Label(sf, text="同步连点数:").grid(row=1, column=0, sticky="w", padx=2)
        self.group_var = tk.StringVar(value=str(group))
        ttk.Entry(sf, textvariable=self.group_var, width=6).grid(row=1, column=1, padx=5)

        self.auto_retry_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(sf, text="自动重试", variable=self.auto_retry_var).grid(
            row=1, column=2, columnspan=2, sticky="w", padx=2)

        ttk.Separator(frame, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)

        self.status_var = tk.StringVar(value="正在启动浏览器...")
        ttk.Label(frame, textvariable=self.status_var, wraplength=280).grid(
            row=3, column=0, columnspan=3, pady=5)

        # 按钮：开始 + 重新开始 + 停止
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(10, 5))
        self.start_btn = ttk.Button(btn_frame, text="开始", command=self.on_start, state="disabled", width=10)
        self.start_btn.pack(side="left", padx=5)
        self.restart_btn = ttk.Button(btn_frame, text="重新开始", command=self.on_restart, state="disabled", width=10)
        self.restart_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.on_stop, state="disabled", width=10)
        self.stop_btn.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(frame, mode="determinate", length=260)
        self.progress.grid(row=5, column=0, columnspan=3, pady=5)

        # 结果
        self.result_var = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.result_var, wraplength=280).grid(
            row=6, column=0, columnspan=3, pady=2)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, msg):
        self.status_var.set(msg)
        self.root.update_idletasks()

    def on_close(self):
        self._stop.set()
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        self.root.destroy()

    def on_stop(self):
        """停止当前执行（包括自动重试循环）"""
        self._stop.set()
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
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def on_restart(self):
        """重新开始：在页面点击重新开始/开始游戏，再次执行点击"""
        self._stop.clear()
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_var.set("")
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

    def _run(self):
        """首次启动：点击开始游戏 → 读取方格 → 连点，勾选自动重试则循环"""
        try:
            size = int(self.size_var.get())
            delay = float(self.delay_var.get())
            group = int(self.group_var.get())
        except ValueError:
            self.root.after(0, lambda: self.log("参数错误，请检查设置"))
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return

        # 选择方格大小
        if size != 5:
            self.log(f"切换到 {size}x{size}...")
            self._select_grid_size(size)

        # 点开始游戏
        self.log("点击开始游戏...")
        if not self._click_start_button():
            self.root.after(0, lambda: self.log("未找到开始游戏按钮"))
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return

        time.sleep(0.15)
        self._do_click(delay, group)

        # 自动重试
        if self.auto_retry_var.get() and not self._stop.is_set():
            self._auto_retry_loop(delay, group)

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _restart(self):
        """重新开始：关弹窗→点重新开始→读方格→连点，勾选自动重试则循环"""
        try:
            delay = float(self.delay_var.get())
            group = int(self.group_var.get())
        except ValueError:
            self.root.after(0, lambda: self.log("参数错误，请检查设置"))
            self.root.after(0, lambda: self.restart_btn.config(state="normal"))
            return

        try:
            self._dismiss_modal()
            time.sleep(0.2)

            self.log("点击重新开始...")
            if not self._click_start_button():
                self.root.after(0, lambda: self.log("未找到重新开始按钮"))
                self.root.after(0, lambda: self.restart_btn.config(state="normal"))
                return

            time.sleep(0.15)
            self._do_click(delay, group)

            # 自动重试
            if self.auto_retry_var.get() and not self._stop.is_set():
                self._auto_retry_loop(delay, group)

        except Exception as e:
            self.root.after(0, lambda: self.log(f"出错: {e}"))

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _auto_retry_loop(self, delay, group):
        """自动重试循环：等1秒 → 关弹窗 → 点重新开始 → 再点一轮"""
        while self.auto_retry_var.get() and not self._stop.is_set():
            self.log("自动重试: 等待1秒...")
            # 分段sleep以便快速响应停止
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
                ok = self._do_click(delay, group)
                if not ok:
                    return
            except Exception as e:
                self.root.after(0, lambda: self.log(f"自动重试出错: {e}"))
                return

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
            self.root.after(0, lambda: self.log(f"完成! 用时 {elapsed:.2f} 秒"))
            self.root.after(0, lambda: self.result_var.set(f"用时: {elapsed:.2f}s, 连点{group}, 间隔{delay}s"))
            return True

        except Exception as e:
            self.root.after(0, lambda: self.log(f"出错: {e}"))
            return False

    def _update_progress(self, num, max_num):
        self.progress["maximum"] = max_num
        self.progress["value"] = num
        self.log(f"点击: {num}/{max_num}")

    def run(self):
        t = threading.Thread(target=self.launch_browser, daemon=True)
        t.start()
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser(description="舒尔特方格速通 v1.0")
    parser.add_argument("--size", type=int, default=5, choices=[4, 5, 6, 7, 8, 9],
                        help="方格大小 (默认5, 即5x5)")
    parser.add_argument("--delay", type=float, default=0.1,
                        help="每组点击之间的间隔秒数 (默认0.1)")
    parser.add_argument("--group", type=int, default=4,
                        help="每组连点数量 (默认4, 1=逐个点击)")
    args = parser.parse_args()

    app = SchulteApp(size=args.size, delay=args.delay, group=args.group)
    app.run()


if __name__ == "__main__":
    main()
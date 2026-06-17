#!/usr/bin/env python3
"""
数字顺序记忆速通 v1.0
https://toolonline.net/number-sequence-memory

python number_sequence_memory_auto.py
"""

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


class NumberSequenceApp:
    def __init__(self, delay=0.05):
        self.delay = delay
        self.driver = None
        self.current_level = 0

        self._running = False
        self._stop = threading.Event()

        self.root = tk.Tk()
        self.root.title("数字顺序记忆速通 v1.0")
        self.root.resizable(False, False)
        self.root.attributes("-topmost", True)

        frame = ttk.Frame(self.root, padding=20)
        frame.pack()

        ttk.Label(frame, text="数字顺序记忆速通 v1.0", font=("", 14, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(0, 10))

        # 设置区
        sf = ttk.LabelFrame(frame, text="设置", padding=8)
        sf.grid(row=1, column=0, columnspan=3, sticky="ew", pady=5)

        ttk.Label(sf, text="点击间隔(秒):").grid(row=0, column=0, sticky="w", padx=2)
        self.delay_var = tk.StringVar(value=str(delay))
        ttk.Entry(sf, textvariable=self.delay_var, width=8).grid(row=0, column=1, padx=5)

        self.auto_next_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(sf, text="自动继续下一关", variable=self.auto_next_var).grid(
            row=0, column=2, columnspan=2, sticky="w", padx=2)

        ttk.Separator(frame, orient="horizontal").grid(row=2, column=0, columnspan=3, sticky="ew", pady=8)

        self.status_var = tk.StringVar(value="正在启动浏览器...")
        ttk.Label(frame, textvariable=self.status_var, wraplength=320).grid(
            row=3, column=0, columnspan=3, pady=5)

        # 按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=4, column=0, columnspan=3, pady=(10, 5))
        self.start_btn = ttk.Button(btn_frame, text="开始", command=self.on_start, state="disabled", width=10)
        self.start_btn.pack(side="left", padx=5)
        self.restart_btn = ttk.Button(btn_frame, text="重新开始", command=self.on_restart, state="disabled", width=10)
        self.restart_btn.pack(side="left", padx=5)
        self.stop_btn = ttk.Button(btn_frame, text="停止", command=self.on_stop, state="disabled", width=10)
        self.stop_btn.pack(side="left", padx=5)

        self.progress = ttk.Progressbar(frame, mode="determinate", length=280)
        self.progress.grid(row=5, column=0, columnspan=3, pady=5)

        # 结果 & 关卡
        info_frame = ttk.Frame(frame)
        info_frame.grid(row=6, column=0, columnspan=3, pady=2)
        self.level_var = tk.StringVar(value="关卡: -")
        ttk.Label(info_frame, textvariable=self.level_var, font=("", 10, "bold")).pack(side="left", padx=10)
        self.result_var = tk.StringVar(value="")
        ttk.Label(info_frame, textvariable=self.result_var).pack(side="left", padx=10)

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
            self.driver.get("https://toolonline.net/number-sequence-memory")

            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".game-area"))
            )

            self.log("浏览器就绪，点击 [开始] 启动测试")
            self.start_btn.config(state="normal")

        except Exception as e:
            self.log(f"启动失败: {e}")
            self.start_btn.config(state="disabled")

    def _click_button_by_text(self, texts):
        """按文字查找并点击黄色按钮，texts为优先级列表"""
        for text in texts:
            try:
                buttons = self.driver.find_elements(By.XPATH, f"//button[contains(.,'{text}')]")
                for btn in buttons:
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        return True
            except Exception:
                pass
        return False

    def on_start(self):
        self._stop.clear()
        self.current_level = 0
        self.start_btn.config(state="disabled")
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_var.set("")
        self.level_var.set("关卡: 1 (4位)")
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def on_restart(self):
        self._stop.clear()
        self.current_level = 0
        self.restart_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.result_var.set("")
        self.level_var.set("关卡: 1 (4位)")
        thread = threading.Thread(target=self._restart, daemon=True)
        thread.start()

    def _run(self):
        """首次启动：点开始测试 → 读取方块 → 按顺序点击"""
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            self.root.after(0, lambda: self.log("参数错误，请检查设置"))
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return

        # 点开始测试
        self.log("点击开始测试...")
        if not self._click_button_by_text(["开始测试"]):
            self.root.after(0, lambda: self.log("未找到开始测试按钮"))
            self.root.after(0, lambda: self.start_btn.config(state="normal"))
            return

        time.sleep(0.5)
        ok = self._play_round(delay, is_first=True)

        # 自动继续下一关
        if ok and self.auto_next_var.get() and not self._stop.is_set():
            self._auto_continue_loop(delay)

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _restart(self):
        """重新开始"""
        try:
            delay = float(self.delay_var.get())
        except ValueError:
            self.root.after(0, lambda: self.log("参数错误"))
            self.root.after(0, lambda: self.restart_btn.config(state="normal"))
            return

        # 尝试点 再试一次 或 开始测试
        self._click_button_by_text(["再试一次", "开始测试", "重新开始"])
        time.sleep(0.5)

        ok = self._play_round(delay, is_first=True)

        if ok and self.auto_next_var.get() and not self._stop.is_set():
            self._auto_continue_loop(delay)

        self.root.after(0, lambda: self.stop_btn.config(state="disabled"))
        self.root.after(0, lambda: self.start_btn.config(state="normal"))
        self.root.after(0, lambda: self.restart_btn.config(state="normal"))

    def _play_round(self, delay, is_first=False):
        """执行一关：等待数字出现 → 读取数字 → 按顺序点击"""
        try:
            # 等待方块出现 (gameState == 1)
            self.log("等待数字出现...")
            blocks = self._wait_for_blocks(timeout=5)
            if not blocks or self._stop.is_set():
                if not self._stop.is_set():
                    self.root.after(0, lambda: self.log("未检测到数字方块"))
                return False

            # 短暂等待让数字渲染完成
            time.sleep(0.3)

            # 读取所有数字方块
            cells = self._read_blocks()
            if not cells:
                self.root.after(0, lambda: self.log("未读取到数字，尝试重新读取..."))
                time.sleep(0.3)
                cells = self._read_blocks()

            if not cells:
                self.root.after(0, lambda: self.log("未读取到数字"))
                return False

            num_count = len(cells)
            max_num = max(cells.keys())
            self.current_level += 1
            self.root.after(0, lambda n=num_count: self.level_var.set(
                f"关卡: {self.current_level} ({n}位)"))
            self.log(f"关卡{self.current_level}: {num_count}个数字, 1-{max_num}")
            self.root.after(0, lambda m=max_num: self.progress.config(maximum=m, value=0))

            start_time = time.time()

            # 按数字从小到大顺序点击
            for i in range(1, max_num + 1):
                if self._stop.is_set():
                    self.root.after(0, lambda: self.log("已停止"))
                    return False

                if i not in cells:
                    self.root.after(0, lambda n=i: self.log(f"数字{n}未找到，重新读取..."))
                    time.sleep(0.1)
                    cells = self._read_blocks()
                    if i not in cells:
                        self.root.after(0, lambda n=i: self.log(f"数字{n}缺失"))
                        continue

                try:
                    cells[i].click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", cells[i])

                n = i
                self.root.after(0, lambda n=n, m=max_num: self._update_progress(n, m))

                if delay > 0 and i < max_num:
                    time.sleep(delay)

            elapsed = time.time() - start_time
            self.root.after(0, lambda e=elapsed: self.log(
                f"关卡{self.current_level}完成! 用时 {e:.2f}秒"))
            self.root.after(0, lambda e=elapsed, n=num_count: self.result_var.set(
                f"关卡{self.current_level}: {n}位, 用时{e:.2f}s"))
            return True

        except Exception as e:
            self.root.after(0, lambda: self.log(f"出错: {e}"))
            return False

    def _wait_for_blocks(self, timeout=5):
        """等待数字方块出现（gameState==1时可见）"""
        start = time.time()
        while time.time() - start < timeout:
            if self._stop.is_set():
                return None
            try:
                # 方块在gameState==1时可见，class为block-number（显示数字）
                blocks = self.driver.find_elements(
                    By.CSS_SELECTOR, ".game-area .block-list .block-number")
                if blocks:
                    # 过滤出有数字文本的
                    numbered = [b for b in blocks if b.text.strip().isdigit()]
                    if numbered:
                        return numbered
                # 也检查block-blank（数字可能已消失）
                blocks = self.driver.find_elements(
                    By.CSS_SELECTOR, ".game-area .block-list .block-blank")
                if blocks:
                    return blocks
            except Exception:
                pass
            time.sleep(0.1)
        return None

    def _read_blocks(self):
        """读取当前可见的数字方块，返回 {数字: WebElement} 字典"""
        cells = {}

        # 方法1：找 block-number 元素（数字可见时）
        try:
            blocks = self.driver.find_elements(
                By.CSS_SELECTOR, ".game-area .block-list .block-number")
            for block in blocks:
                text = block.text.strip()
                if text.isdigit():
                    cells[int(text)] = block
            if cells:
                return cells
        except Exception:
            pass

        # 方法2：找所有 block 元素
        try:
            blocks = self.driver.find_elements(
                By.CSS_SELECTOR, ".game-area .block-list .block")
            for block in blocks:
                text = block.text.strip()
                if text.isdigit():
                    cells[int(text)] = block
            if cells:
                return cells
        except Exception:
            pass

        # 方法3：通过JS直接读取Vue数据
        try:
            result = self.driver.execute_script("""
                var blocks = document.querySelectorAll('.game-area .block-list .block');
                var data = [];
                for (var i = 0; i < blocks.length; i++) {
                    var txt = blocks[i].textContent.trim();
                    if (txt && !isNaN(txt)) {
                        data.push({num: parseInt(txt), index: i});
                    }
                }
                return JSON.stringify(data);
            """)
            if result:
                import json
                items = json.loads(result)
                blocks = self.driver.find_elements(
                    By.CSS_SELECTOR, ".game-area .block-list .block")
                for item in items:
                    idx = item['index']
                    num = item['num']
                    if idx < len(blocks):
                        cells[num] = blocks[idx]
                if cells:
                    return cells
        except Exception:
            pass

        return cells

    def _auto_continue_loop(self, delay):
        """自动继续循环：等1秒 → 点击继续 → 下一关"""
        while self.auto_next_var.get() and not self._stop.is_set():
            self.log("等待1秒...")
            for _ in range(10):
                if self._stop.is_set():
                    return
                time.sleep(0.1)

            try:
                # 先尝试点"继续"按钮
                self.log("点击继续...")
                clicked = self._click_button_by_text(["继续"])
                if not clicked:
                    # 可能是失败界面，尝试"再试一次"
                    clicked = self._click_button_by_text(["再试一次"])
                    if clicked:
                        self.current_level = 0
                        time.sleep(0.5)
                        # 再试一次后不需要额外点击开始
                        ok = self._play_round(delay)
                        if not ok:
                            return
                        continue
                    else:
                        self.root.after(0, lambda: self.log("未找到继续/重试按钮"))
                        return

                time.sleep(0.5)
                ok = self._play_round(delay)
                if not ok:
                    return

            except Exception as e:
                self.root.after(0, lambda: self.log(f"自动继续出错: {e}"))
                return

    def _update_progress(self, num, max_num):
        self.progress["maximum"] = max_num
        self.progress["value"] = num
        self.log(f"点击: {num}/{max_num}")

    def run(self):
        t = threading.Thread(target=self.launch_browser, daemon=True)
        t.start()
        self.root.mainloop()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="数字顺序记忆速通 v1.0")
    parser.add_argument("--delay", type=float, default=0.05,
                        help="每次点击间隔秒数 (默认0.05)")
    args = parser.parse_args()

    app = NumberSequenceApp(delay=args.delay)
    app.run()


if __name__ == "__main__":
    main()
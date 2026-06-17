# toolonline-hacks

> ⚠️ **免责声明 / Disclaimer**
>
> 本仓库中的脚本仅供**学习与研究用途**，旨在探索浏览器自动化技术与 DOM 元素识别方法。
> 使用者需自行承担所有风险与责任，作者不对任何滥用行为负责。
>
> These scripts are for **educational and research purposes only**, intended to explore browser automation and DOM element recognition techniques.
> Users bear full responsibility for their actions; the author is not liable for any misuse.

---

[toolonline.net](https://toolonline.net) 小游戏速通脚本集合。基于 Selenium + ChromeDriver 自动化浏览器，通过 DOM 元素识别取代传统 OCR，速度更快、准确率更高。

## 脚本列表

### 1. 舒尔特方格速通 — [`scripts/schulte_auto.py`](scripts/schulte_auto.py)

**目标游戏**: [舒尔特方格](https://toolonline.net/shult-grid)

**功能**: 自动识别方格中的数字，按 1→N 顺序快速点击完成测试。

**特性**:

- 支持 4×4 ~ 9×9 方格大小选择
- 连点模式：每 N 个数字为一组快速点击，组间短暂延迟，兼顾速度与稳定性
- 自动重试：完成一轮后自动开始下一轮
- 重新开始按钮：无需重启脚本，一键再来
- GUI 控制面板：棋盘阶级、点击间隔、同步连点数均可界面设置

**使用方法**:

```bash
python scripts/schulte_auto.py
```

启动后弹出 GUI 窗口和浏览器：

1. 浏览器打开游戏页面，在 GUI 设置参数（方格大小、间隔、连点数等）
2. 点击 GUI 的 **「开始」** 按钮
3. 脚本自动点击页面"开始游戏"并执行速通
4. 完成后可点击 **「重新开始」** 再次尝试，无需重启

**参数说明**:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 棋盘阶级 | 5 (5×5) | 可选 4~9 |
| 间隔(秒) | 0.1 | 每组连点之间的延迟 |
| 同步连点数 | 4 | 每组连续点击几个数字再延迟，1=逐个点击 |
| 自动重试 | 关 | 勾选后完成后自动重新开始 |

---

### 2. 数字顺序记忆速通 — [`scripts/number_sequence_memory_auto.py`](scripts/number_sequence_memory_auto.py)

**目标游戏**: [数字顺序记忆](https://toolonline.net/number-sequence-memory)

**功能**: 自动识别屏幕上的数字方块，按从小到大顺序依次点击，并支持自动闯关。

**特性**:

- 多策略数字识别：`block-number` CSS 选择器 → 通用 `block` 选择器 → Vue 数据直接读取，三层递进确保识别成功率
- 自动闯关：完成一关后自动点击"继续"进入下一关
- 重新开始：一键重试，无需重启脚本
- 关卡进度显示：实时显示当前关卡和数字位数
- 数字缺失自动重读：点击过程中发现数字消失会重新读取 DOM

**使用方法**:

```bash
python scripts/number_sequence_memory_auto.py
```

启动后弹出 GUI 窗口和浏览器：

1. 浏览器打开游戏页面
2. 在 GUI 设置点击间隔（默认 0.05 秒）
3. 点击 GUI 的 **「开始」** 按钮
4. 脚本等待数字出现后自动按顺序点击
5. 勾选「自动继续下一关」可自动闯关

**参数说明**:

| 参数 | 默认值 | 说明 |
|------|--------|------|
| 点击间隔(秒) | 0.05 | 每次点击之间的延迟 |
| 自动继续下一关 | 开 | 勾选后完成一关自动进入下一关 |

---

## 依赖

脚本启动时会自动检测并安装：

- Python 3.8+
- [selenium](https://pypi.org/project/selenium/) — 浏览器自动化
- [webdriver-manager](https://pypi.org/project/webdriver-manager/) — ChromeDriver 自动管理
- tkinter — GUI 界面（Python 自带）

也可手动安装：

```bash
pip install selenium webdriver-manager
```

## 原理

| 传统 OCR 方式 | 本项目方式 |
|---------------|-----------|
| 截图 → 图像识别 → 坐标换算 → 点击 | DOM 选择器定位 → element.click() |
| 延迟高、识别率受截图影响 | 延迟低、100% 准确 |
| 需要额外 OCR 依赖 | 无额外依赖 |

- 基于 Selenium WebDriver 直接操作浏览器 DOM 元素
- `WebElement.click()` 直接触发点击事件，无需坐标换算
- JS 点击（`arguments[0].click()`）作为 fallback，应对元素被遮挡等情况
- 多线程架构：识别线程预规划路径，点击线程同步执行

## License

[MIT](LICENSE)

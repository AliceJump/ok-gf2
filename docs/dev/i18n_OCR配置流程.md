# i18n 与 OCR 配置流程

本文记录当前项目中运行时语言、OCR 文本匹配和 OCR 纠错的实际链路，适用于新增任务、补充翻译、维护 OCR 匹配文本时参考。

---

## 总体链路

```text
ok-script executor.locale / task.locale
        ↓
BaseGfTask.runtime_locale
        ↓
ocr / wait_ocr / wait_click_ocr / 业务比较
```

---

## 运行时语言来源

通过 `executor.locale` 获取当前 UI 显示语言。

当前支持的游戏语言：
- 简体中文（zh_CN）
- 英文（en_US）

---

## OCR 识别

### 基本 OCR

```python
# 全屏 OCR
result = self.ocr()

# 区域 OCR
result = self.ocr(box=self.box.bottom, match="确认")

# 正则匹配
result = self.ocr(match=re.compile(r"\d+"))
```

### 等待并识别

```python
# 等待直到匹配
result = self.wait_ocr(match="确认", time_out=10)

# 等待并点击
self.wait_click_ocr(match="开始", time_out=8)
```

### 带预处理 OCR

支持传入 `frame_processor` 参数进行图像预处理后再识别：

```python
# 标准白色过滤
processor = self.make_hsv_isolator(hR.WHITE)
result = self.ocr(box=box, match=pattern, frame_processor=processor)

# 宽松白灰色过滤
processor = self.make_hsv_isolator(hR.WHITE_GRAY)
result = self.ocr(box=box, match=pattern, frame_processor=processor)
```

### OCR 计数检测

```python
# 等待 OCR 检测到至少 N 个匹配对象
results = self.wait_ocr_until_count(match="目标", min_count=2, timeout=5)
```

---

## 弹窗处理

通用弹窗匹配列表定义在 `BaseGfTask.pop_ups`：

```python
pop_ups = ["点击空白处关闭", "点击屏幕任意位置继续", "点击任意位置继续", "新周期开启"]
```

通过 `wait_pop_up()` 方法自动检测并关闭弹窗。

---

## 常用正则表达式

```python
number_re = re.compile(r"^\d+$")  # 纯数字
stamina_re = re.compile(r"^\d+/\d+")  # 体力值 (如 120/120)
map_re = re.compile(r"^.{0,2}\s*-?\s*\d{1,2}\s*-\s*\d{1,2}\s*\*?$")  # 地图关卡名
```

---

## 新增 OCR 匹配文本流程

1. 确定需要匹配的文本内容。
2. 在代码中直接使用字符串或正则表达式进行匹配。
3. 对于可能变化的文本（如关卡名、数字），优先使用正则表达式。
4. 对于固定按钮文本，直接使用字符串匹配。

---

## 注意事项

- OCR 识别受图像质量、字体、背景颜色等因素影响。
- 主页背景必须使用暗色，白色背景会导致 OCR 识别失败。
- 如遇 OCR 识别错误，可在调试模式下运行并查看截图目录下的截图。

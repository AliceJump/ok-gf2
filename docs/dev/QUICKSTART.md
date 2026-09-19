# ok-gf2 开发者快速开始

> 目标读者：希望为 ok-gf2 贡献代码的开发者。

---

## 1. 从源码运行项目

### 1.1 环境要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows |
| Python | **3.12**（仅支持此版本） |
| 运行权限 | **管理员权限**（必须；需以管理员身份启动 CMD / PyCharm / VSCode） |
| 安装路径 | 纯英文路径（例如 `D:\dev\ok-gf2`），不要含中文或空格 |

### 1.2 克隆仓库

```bash
git clone --recurse-submodules https://github.com/alicejump/ok-gf2.git
cd ok-gf2
```

> 项目包含子模块，务必加上 `--recurse-submodules`。

若你已 clone 但忘记带 `--recurse-submodules`，可补执行：

```bash
git submodule update --init --recursive
```

### 1.3 安装依赖

```bash
# CPU 版本
pip install -r requirements.txt --upgrade

# CUDA 版本（N 卡 30 系以上）
pip install -r requirements-dml.txt --upgrade
```

### 1.4 启动程序

```bash
# Release 模式
python main.py

# Debug 模式（截图/日志更详细，推荐开发时使用）
python main_debug.py
```

---

## 2. 新建一个任务

### 2.1 创建任务文件

在 `src/tasks/` 下新建文件，例如 `MyTask.py`：

```python
from src.core.BaseGfTask import BaseGfTask

class MyTask(BaseGfTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "我的任务"
        self.description = "在此描述任务功能"
        self.default_config = {"选项A": True}
        self.config_description = {"选项A": "选项A的说明"}

    def run(self):
        self.ensure_main()
        # 在此编写业务逻辑
        self.log_info("任务执行完成")
```

### 2.2 注册任务

打开 `src/config.py`，将新任务加入 `onetime_tasks` 列表：

```python
"onetime_tasks": [
    ...
    ["src.tasks.MyTask", "MyTask"],  # 新增
],
```

### 2.3 运行与验证

重新启动程序（`python main_debug.py`），在 GUI 任务列表中即可看到并运行新任务。

---

## 后续阅读

| 文档 | 说明 |
|------|------|
| [开发指南 (DEVELOPMENT.md)](DEVELOPMENT.md) | 架构总览、目录结构、开发流程 |
| [API 参考 (API.md)](API.md) | BaseGfTask、Mixin 等详细 API |
| [键盘操作体系](键盘操作体系.md) | 热键映射、按键封装规范 |
| [i18n 与 OCR 配置流程](i18n_OCR配置流程.md) | 语言 JSON、OCR 匹配与纠错 |

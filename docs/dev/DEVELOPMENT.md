# ok-gf2 开发文档

> 本文档面向希望参与或了解 ok-gf2 项目开发的开发者，涵盖项目架构、目录结构、各文件职责、开发流程与测试。

---

## 目录

1. [项目概览](#1-项目概览)
2. [架构总览](#2-架构总览)
3. [目录结构与文件职责](#3-目录结构与文件职责)
4. [开发环境搭建](#4-开发环境搭建)
5. [开发流程](#5-开发流程)
6. [测试](#6-测试)

---

## 1. 项目概览

**ok-gf2** 是基于 [ok-script](https://github.com/ok-oldking/ok-script) 框架开发的《少女前线2：追放》游戏自动化工具。

核心技术栈：

| 层次 | 技术 |
|------|------|
| 底层框架 | ok-script（截图、OCR、模板匹配、UI） |
| 截图 | WGC / BitBlt（Windows） |
| OCR | OnnxOCR + OpenVINO 加速 |
| 模板匹配 | OpenCV TM_CCOEFF_NORMED |
| UI | PyQt6 / PySide6 + PyQt-Fluent-Widgets |
| 交互 | Windows PostMessage / Win32 API |
| 语言 | Python 3.12（仅支持此版本） |
| 打包 | PyAppify |

---

## 2. 架构总览

```
main.py / main_debug.py / main_direct_ml.py
        │
        ▼
   ok.OK(config)          ← ok-script 框架主入口，负责窗口捕获、任务调度、GUI
        │
        ├── onetime_tasks  ← 用户点击触发的一次性任务
        │       ├── DailyTask           (日常任务)
        │       ├── WeeklyTask          (周常任务)
        │       ├── ClearMapTask        (清图/推图)
        │       ├── PioneersTask        (兵棋推演/开拓之王)
        │       ├── TestStartGame       (测试启动游戏)
        │       ├── TestTask            (开发调试用)
        │       └── DiagnosisTask       (诊断)
        │
        └── trigger_tasks  ← 后台持续运行的触发式任务（未来扩展）
```

### 继承链（DailyTask 为例）

```
DailyTask
 └── CommunityMixin (社区每日)
 └── BaseGfTask
      └── BaseTask (ok-script 框架基类)
```

---

## 3. 目录结构与文件职责

```
ok-gf2/
├── main.py                    # 正式版入口：启动 ok.OK(config)
├── main_debug.py              # 调试版入口：config['debug']=True
├── main_direct_ml.py          # CUDA 加速版入口
├── requirements.in            # 顶层依赖
├── requirements.txt           # CPU 版完整锁定依赖
├── requirements-dml.in        # DirectML 版依赖
├── requirements-dml.txt       # DirectML 版完整锁定依赖
├── pyappify.yml               # PyAppify 打包配置
├── deploy.txt                 # 部分同步到更新库的文件列表
├── run_tests.ps1              # 本地一键跑所有单元测试（PowerShell）
├── auto_release.ps1           # 辅助打版本 tag 的脚本
│
├── src/                       # 项目核心源码
│   ├── config.py              # 配置字典（传给 ok.OK），定义所有任务列表、窗口参数、OCR 参数等
│   ├── globals.py             # 全局单例（Globals），存放跨任务共享状态
│   ├── region.py              # Region 设置（Global / CN），追加国际服任务并隐藏未选中的一侧
│   │
│   ├── data/
│   │   ├── FeatureList.py     # 枚举：所有模板匹配特征名
│   │   └── features.py        # 特征数据
│   │
│   ├── image/                 # 图像处理工具层
│   │   ├── frame_processs.py  # HSV 颜色掩码提取
│   │   └── hsv_config.py      # HSVRange 枚举
│   │
│   ├── interaction/           # 游戏交互层（Windows 专用）
│   │   ├── Key.py             # 按键映射
│   │   ├── Mouse.py           # 鼠标辅助
│   │   └── ScreenPosition.py  # 屏幕坐标工具
│   │
│   ├── scheduler/             # 计划任务
│   │   └── windows_schedule.py
│   │
│   ├── ui/                    # UI 页面
│   │   └── TaskSchedulerTab.py
│   │
│   ├── js/                    # JavaScript 脚本
│   │
│   └── tasks/                 # 任务层（业务逻辑核心）
│       ├── BaseGfTask.py      # 所有任务的公共基类（继承自 BaseTask）
│       ├── DailyTask.py       # 日常任务
│       ├── WeeklyTask.py      # 周常任务
│       ├── ClearMapTask.py    # 清图/推图任务
│       ├── PioneersTask.py    # 兵棋推演/开拓之王
│       ├── CommunityClient.py # 社区每日 API 客户端
│       ├── TestStartGame.py   # 测试启动游戏
│       └── TestTask.py        # 开发调试用
│
│   └── global/                # 国际服（Steam 英文版）任务层，直接匹配英文文本
│       ├── BaseGlobalTask.py  # 国际服任务基类，覆盖所有与中文绑定的方法
│       ├── GlobalDailyTask.py # 国际服日常
│       ├── GlobalWeeklyTask.py# 国际服周常
│       └── VerifyTasks.py     # 每个流程一个任务，用于单独验证
│
├── assets/                    # 静态资源
│   ├── coco_annotations.json  # COCO 格式标注
│   ├── images/                # 模板匹配图片
│   └── ppocr_keys_v1.txt      # OCR 字典
│
├── tools/                     # 开发辅助工具
│   └── record_walk.py         # 记录公共区行走按键时长，用于填写 Crew Deck 的行走设置
│
├── docs/                      # 功能说明文档
│   ├── 日常任务.md
│   ├── 清图任务.md
│   ├── 兵棋推演.md
│   ├── 周常任务.md
│   ├── glossary.md            # 中文 -> 国际服英文术语对照
│   ├── en/                    # 英文版用户文档
│   └── dev/                   # 面向开发者的技术文档
│       ├── QUICKSTART.md
│       ├── DEVELOPMENT.md
│       ├── API.md
│       ├── i18n_OCR配置流程.md
│       └── 键盘操作体系.md
│
├── configs/                   # 任务/全局配置（JSON）
│
├── ok_templates/              # 子模块：AnyLabeling 标注工具配置
│
├── logs/                      # 运行日志与线程转储
│
├── screenshots/               # 运行时截图目录
│
├── i18n/                      # 国际化翻译文件
│
├── icons/                     # 程序图标
│
└── tests/                     # 单元测试
    ├── TestMain.py
    ├── TestEnglish.py
    └── TestOcr.py
```

---

## 4. 开发环境搭建

### 前提条件

- Windows 10/11（必须，依赖 Win32 API）
- Python **3.12**（严格要求，其它版本不受支持）
- **管理员权限**启动 IDE 或 CMD

### 安装步骤

```bash
# 1. 克隆项目
git clone --recurse-submodules https://github.com/alicejump/ok-gf2.git
cd ok-gf2

# 若首次 clone 未带子模块参数，可补执行
git submodule update --init --recursive

# 2. 安装依赖
pip install -r requirements.txt --upgrade

# 3. 运行 Debug 版本
python main_debug.py
```

---

## 5. 开发流程

### 5.1 新增一次性任务

1. 在 `src/tasks/` 下新建 `MyTask.py`，继承 `BaseGfTask`：

   ```python
   from src.tasks.BaseGfTask import BaseGfTask

   class MyTask(BaseGfTask):
       def __init__(self, *args, **kwargs):
           super().__init__(*args, **kwargs)
           self.name = "我的任务"
           self.description = "任务说明"
           self.default_config = {"选项A": True}
           self.config_description = {"选项A": "选项A的说明"}

       def run(self):
           self.ensure_main()
           # 业务逻辑
   ```

2. 在 `src/config.py` 的 `onetime_tasks` 列表中注册：

   ```python
   ["src.tasks.MyTask", "MyTask"],
   ```

### 5.2 添加新的模板图片（Feature）

1. 在 `ok_templates/` 中添加或更新标注文件。
2. 运行 `compress.py` 导出并替换到 `assets/images`。
3. 程序会自动更新 `src/data/FeatureList.py`。
4. 在代码中通过 `self.find_feature(fL.my_new_feature)` 调用新特征。

### 5.3 添加新的 OCR 识别逻辑

- 使用 `self.ocr(box=..., match=re.compile("关键字"))` 进行区域 OCR。
- 使用 `self.wait_ocr(match=..., time_out=5)` 等待并返回结果。
- 使用 `self.wait_click_ocr(match=..., box=..., time_out=5)` 等待并点击。

---

## 6. 测试

### 运行全部测试

```powershell
# PowerShell（Windows）
./run_tests.ps1
```

```bash
# 或逐个运行
python -m unittest tests/TestMain.py
python -m unittest tests/TestOcr.py
```

### 测试文件说明

| 文件 | 测试内容 |
|------|----------|
| `TestMain.py` | 主要功能测试 |
| `TestEnglish.py` | 英文语言测试 |
| `TestOcr.py` | OCR 识别测试 |
| `TestGlobalMain.py` | 国际服任务测试：主界面识别、各流程提前退出的判断、光标被占用时的恢复 |

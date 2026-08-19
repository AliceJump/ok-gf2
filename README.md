<p align="center">
  <img 
    src="icons/icon.png"
    alt="ok-gf2 game automation tool logo"
    width="256"
    height="256"
  />
</p>

<h1 align="center">ok-gf2</h1>

<p>
基于图像识别的少前2（Girls' Frontline 2）自动化程序，部分功能支持后台运行，基于 <a href="https://github.com/ok-oldking/ok-script">ok-script</a> 开发。
<br />
An image-recognition-based automation tool for Girls' Frontline 2, with background mode support, developed with <a href="https://github.com/ok-oldking/ok-script">ok-script</a>.
</p>

<p><i>通过模拟 Windows 用户接口进行操作，无内存读取、无文件修改</i></p>


<!-- Badges -->
<div align="center">

![平台](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/alicejump/ok-gf2)](https://github.com/alicejump/ok-gf2/releases)
[![总下载量](https://img.shields.io/github/downloads/alicejump/ok-gf2/total)](https://github.com/alicejump/ok-gf2/releases)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/AliceJump/ok-gf2)

</div>

### 中文说明 | [English Readme](README_en.md)

---

## ⚠️ 免责声明

本软件为外部辅助工具，旨在自动化《少前2：追放》的部分游戏流程。它完全通过模拟常规用户界面与游戏交互，遵循相关法律法规。本项目旨在简化用户的重复性操作，不会破坏游戏平衡或提供不公平优势，也绝不会修改任何游戏文件或数据。

本软件开源、免费，仅供个人学习与交流使用，请勿用于任何商业或营利性目的。开发者团队拥有本项目的最终解释权。因使用本软件而产生的任何问题，均与本项目及开发者无关。

**使用本软件即表示您已阅读、理解并同意以上声明，并自愿承担一切潜在风险。**

## 🚀 快速开始

1. **下载安装包**：从下方的"下载渠道"中选择一个，下载最新的 `ok-gf2` 压缩包。
2. **解压运行**：解压后双击 `ok-gf2.exe` 即可运行，下载后可应用内更新。
3. **配置任务**：根据需求在软件界面配置任务参数并执行。

## 📥 下载渠道

* **[GitHub](https://github.com/alicejump/ok-gf2/releases)**: 官方发布页，全球访问速度快。（**请下载 `7z` 压缩包，而不是 `Source Code` 源码压缩包**）
* **[Mirror酱](https://mirrorchyan.com/zh/projects?rid=okgf2&source=okgf2readme)**: 国内镜像，下载可能需要购买其平台的 CD-KEY。
* **[夸克网盘](https://pan.quark.cn/s/a1052cec4d13)**: 免费下载（需注册并下载夸克网盘客户端）

## 运行要求与推荐设置

- 系统：Windows
- 游戏：直接使用 PC 版少前2，可原生后台运行
- 分辨率：支持所有 16:9 分辨率
- 帧率：推荐 120 FPS，帧率越高越好
- 语言：支持简体中文 / 英文（英文可能有不少问题）
- 显示：Windows 自动 HDR 必须关闭，可以使用 RTX HDR
- 背景：主页背景需要使用**暗色**，不能用白色背景，不然识别不到文字
- 运行权限：建议管理员权限运行（源码模式必须）
- 路径：安装/运行路径尽量使用纯英文

---

## 🎮 功能一览

### 一次性任务

- **[日常任务](docs/日常任务.md)**：一键长草，完成每日例行的各项操作
- **[清图任务](docs/清图任务.md)**：自动清理地图关卡
- **[兵棋推演](docs/兵棋推演.md)**：自动进行兵棋推演玩法
- **活动体力扫荡**：自动扫荡活动关卡消耗体力
- **竞技场**：自动进行竞技场战斗
- **尘烟前线**：自动完成尘烟玩法
- **要务**：自动完成要务任务
- **[周常任务](docs/周常任务.md)**：自动完成每周例行任务
- **诊断**：框架内置诊断任务的简单封装

### 触发任务（后台运行）

- **自动战斗**：检测战斗状态并按技能序列自动释放
- **自动拾取**：自动拾取关卡中掉落的物品
- **自动交互**：自动跳过剧情对话

### 定时任务

- 支持将一次性任务加入 Windows 任务计划，按设定时间自动启动执行

### 辅助能力

- OCR 识别、模板匹配、HSV 颜色识别
- UI 自动化、按键模拟
- 日志、异常处理、流程调度

---

## ⚙️ 部分参数说明

### 1. 当前物资关卡名称

- 若为 **小活动**，物资关卡会显示为 **物资模式**，此时无需填写任何内容。
- 若为 **大活动**，物资关卡会显示为 **铸碑者的黎明·上篇**，则需要填写物资关卡名为 **铸碑者的黎明**。

> ⚠️ 不正确填写可能会影响活动代理逻辑。

![image](https://github.com/user-attachments/assets/ed261840-449a-46d4-8a07-f58382f3a779)

---

### 2. 已确认启用游戏内全局自动功能

路径：**设置 → 其他 → 自动战斗设置**

---

### 3. 喝水

逻辑：进入活动层后先按 `A` 后按 `W` 再按 `D`，需自行调整。
使用格式：`{A按住秒数}-{W按住秒数}-{D按住秒数}`
示例：`1.44-1.56-1.38`

---

### 4. 吃饭

逻辑：进入活动层后先按 `S` 后点按 `D`，需自行调整。
使用格式：`{S按住秒数}`
示例：`1.3`

---

![image](https://github.com/user-attachments/assets/6bd2ac34-fd40-4c74-9e8e-a0343818876d)

![image](https://github.com/user-attachments/assets/ae1ecd07-6608-478d-9226-40d4f8000a60)

---

## 🔧 疑难解答 (Troubleshooting)

如果遇到问题，请在提问前按以下步骤逐一排查：

1. **安装路径**：请确保软件安装在**纯英文路径**下，避免包含中文字符的文件夹。
2. **杀毒软件**：将软件的安装目录添加到您的杀毒软件（包括 Windows Defender）的**信任区或白名单**中，以防文件被误删或拦截。
3. **显示设置**：
   * 关闭 Windows 自动 HDR（必须），可以使用 RTX HDR。
   * 使用游戏默认的亮度设置。
   * 主页背景使用**暗色**，不能用白色背景。
4. **游戏帧率**：推荐 **120 FPS**，帧率越高越好。
5. **游戏语言**：优先使用简体中文，英文可能有部分问题。
6. **软件版本**：检查并确保您使用的是最新版本。
7. **寻求帮助**：如果以上步骤都无法解决您的问题，请通过 QQ 群提交详细的错误报告。

## 💬 加入我们

* **QQ 交流群**：`1033950808`（入群答案：`老王同学OK`）

本项目基于 [ok-script](https://github.com/ok-oldking/ok-script) 框架开发，简单易维护。欢迎有兴趣的开发者使用 [ok-script](https://github.com/ok-oldking/ok-script) 开发您自己的自动化项目。

## 🔗 使用 ok-script 的项目

* 终末地 [https://github.com/AliceJump/ok-end-field](https://github.com/AliceJump/ok-end-field)
* 鸣潮 [https://github.com/ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)
* 鸣潮（日常一条龙-优化版）[https://github.com/zzc-tongji/ok-ww-enhanced](https://github.com/zzc-tongji/ok-ww-enhanced)
* 原神（停止维护，后台过剧情可用）[https://github.com/ok-oldking/ok-genshin-impact](https://github.com/ok-oldking/ok-genshin-impact)
* 少前2 [https://github.com/ok-oldking/ok-gf2](https://github.com/ok-oldking/ok-gf2)
* 星铁 [https://github.com/Shasnow/ok-starrailassistant](https://github.com/Shasnow/ok-starrailassistant)
* 星痕共鸣 [https://github.com/Sanheiii/ok-star-resonance](https://github.com/Sanheiii/ok-star-resonance)
* 二重螺旋 [https://github.com/BnanZ0/ok-duet-night-abyss](https://github.com/BnanZ0/ok-duet-night-abyss)
* 白荆回廊（停止更新）[https://github.com/ok-oldking/ok-baijing](https://github.com/ok-oldking/ok-baijing)

---

## 💻 开发者专区

### 从源码运行 (Python)

本项目仅支持 Python 3.12 版本，需以管理员权限启动 CMD / PyCharm / VSCode。

```bash
# 如果首次 clone 未带子模块参数，请先执行
git submodule update --init --recursive

# CPU 版本，使用 OpenVINO
pip install -r requirements.txt --upgrade

# 运行 Release 版本
python main.py

# 运行 Debug 版本
python main_debug.py
```

```bash
# CUDA 版本，使用 paddle-gpu 加速，推荐 N 卡 30 系以上使用，速度飞快
pip install -r requirements-dml.txt --upgrade

# 运行 Release 版本
python main_direct_ml.py

# 运行 Debug 版本
python main_direct_ml_debug.py
```

### 命令行参数

您可以通过命令行参数实现自动化启动。

```pwsh
# 启动后自动执行第1个任务，并在任务完成后退出程序
ok-gf2.exe -t 1 -e
```

- `-t` 或 `--task`：启动后自动执行第 N 个任务。
- `-e` 或 `--exit`：任务执行完毕后自动退出程序。

### 开发调试与测试

```bash
# 执行 tests/ 下全部测试脚本（PowerShell）
./run_tests.ps1

# 或逐个运行 unittest
python -m unittest tests/TestMain.py
```

### 开发者文档

| 文档 | 说明 |
|------|------|
| [快速开始（QUICKSTART.md）](docs/dev/QUICKSTART.md) | 从源码运行项目、启动软件、新建任务的最简流程 |
| [开发指南（DEVELOPMENT.md）](docs/dev/DEVELOPMENT.md) | 架构总览、目录结构、开发流程、测试、CI/CD |
| [API 参考（API.md）](docs/dev/API.md) | BaseGfTask、Mixin、ScreenPosition 等详细 API |
| [i18n 与 OCR 配置流程](docs/dev/i18n_OCR配置流程.md) | runtime locale、语言 JSON、OCR 匹配与纠错配置流程 |
| [键盘操作体系](docs/dev/键盘操作体系.md) | 热键映射、按键封装规范 |

## ❤️ 赞助与致谢

### 赞助商 (Sponsors)

[![爱发电](https://img.shields.io/badge/爱发电-赞助-blue?style=flat-square)](https://afdian.com/a/AliceJump)
[![爱发电](https://img.shields.io/badge/爱发电-赞助-blue?style=flat-square)](https://afdian.com/a/ok-oldking)
[![Patreon](https://img.shields.io/badge/Patreon-支持-orange?style=flat-square)](https://patreon.com/ok_oldking)
[![PayPal](https://img.shields.io/badge/PayPal-捐赠-blue?style=flat-square)](https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ)

### 致谢

* [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
* [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script)

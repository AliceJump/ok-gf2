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
An image-recognition-based automation tool for Girls' Frontline 2, with background mode support, developed with <a href="https://github.com/ok-oldking/ok-script">ok-script</a>.
<br />
Automates parts of Girls' Frontline 2 via screen recognition and simulated user inputs.
</p>

<p><i>Operates by simulating Windows user input. No memory reading, no file modification.</i></p>


<!-- Badges -->
<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/alicejump/ok-gf2)](https://github.com/alicejump/ok-gf2/releases)
[![Total downloads](https://img.shields.io/github/downloads/alicejump/ok-gf2/total)](https://github.com/alicejump/ok-gf2/releases)

</div>

### [中文说明](README.md) | English Readme

---

## ⚠️ Disclaimer

This software is an external assistance tool intended to automate parts of Girls' Frontline 2. It interacts with the game by
simulating normal user interface operations and complies with relevant laws and regulations. The project aims to reduce
repetitive actions, does not break game balance or provide unfair advantages, and never modifies any game files or data.

This software is open-source and free for personal learning and communication only. Commercial or profit-oriented use is
prohibited. The development team reserves the right of final interpretation. Any issues arising from use of this
software are unrelated to the project or its developers.

**By using this software, you acknowledge that you have read, understood, and agreed to the above statement and assume
all potential risks.**

## 🚀 Quick Start

1. **Download the package**: Choose a source below and download the latest `ok-gf2` archive.
2. **Extract and run**: Extract the archive and double-click `ok-gf2.exe` to run.
3. **Configure tasks**: Set up task parameters in the software interface as needed.

## 📥 Download Sources

* **[GitHub](https://github.com/alicejump/ok-gf2/releases)**: Official release page with fast global access. (**Download the `7z` archive, not the `Source Code` archive**)
* **[Mirrorchyan](https://mirrorchyan.com/zh/projects?rid=okgf2&source=okgf2readme)**: China mirror (may require a CD-KEY purchase).
* **[Quark Drive](https://pan.quark.cn/s/80730a808d0e)**: Free download (requires registration and Quark Drive client).
* **[Baidu Netdisk](https://pan.baidu.com/s/102Mh1djq2B1T-cIJhct9Gg?pwd=okww)**: Free download (extraction code: `okww`).

## Runtime Requirements & Recommendations

- OS: Windows
- Game: PC version of Girls' Frontline 2, supports native background mode
- Resolution: All 16:9 resolutions supported
- Frame rate: 120 FPS recommended, higher is better
- Language: Simplified Chinese / English (English may have issues)
- Display: Windows Auto HDR must be disabled, RTX HDR is acceptable
- Background: **Dark** home screen background required (white background causes recognition failure)
- Privilege: Run as Administrator recommended (required for source mode)
- Path: Prefer pure-English install/runtime path

---

## 🎮 Feature Overview

### One-time tasks

- **Daily Task**: One-click daily routine operations
- **Clear Map Task**: Auto clear map stages
- **Pioneers Task**: Auto play pioneers mode
- **Event Stamina Sweep**: Auto sweep event stages
- **Arena**: Auto battle in arena
- **Dust Front**: Auto complete dust front mode
- **Commission**: Auto complete commission tasks
- **Weekly Task**: Auto complete weekly tasks
- **Diagnosis**: Simple wrapper around the built-in framework diagnosis task

### Trigger tasks (background loop detection)

- **Auto Combat**: Battle-state detection and automatic skill release
- **Auto Pickup**: Auto pickup dropped items
- **Auto Interaction**: Auto skip story dialogs

### Scheduled tasks
- You can add one-time tasks into Windows Task Scheduler for automatic launch

---

## 🔧 Troubleshooting

If you encounter issues, check the following in order:

1. **Install path**: Install under a pure English path. Avoid folders with non-ASCII characters.
2. **Antivirus**: Add the install directory to your antivirus (including Windows Defender) allow-list.
3. **Display settings**:
   * Disable Windows Auto HDR (required), RTX HDR is acceptable.
   * Use the game's default brightness settings.
   * Use **dark** home screen background.
4. **Game frame rate**: **120 FPS** recommended, higher is better.
5. **Game language**: Simplified Chinese preferred, English may have issues.
6. **Software version**: Ensure you're running the latest release.
7. **Get help**: If all above fails, submit a detailed error report via the QQ group.

## 💬 Join Us

* **QQ Group**: `1033950808` (answer: `老王同学OK`)

This project is built on [ok-script](https://github.com/ok-oldking/ok-script), which is easy to maintain. Developers are
welcome to build their own automation projects with ok-script.

## 🔗 Projects using ok-script

* End Field [https://github.com/AliceJump/ok-end-field](https://github.com/AliceJump/ok-end-field)
* Wuthering Waves [https://github.com/ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)
* Wuthering Waves (Enhanced) [https://github.com/zzc-tongji/ok-ww-enhanced](https://github.com/zzc-tongji/ok-ww-enhanced)
* Genshin Impact (maintenance stopped) [https://github.com/ok-oldking/ok-genshin-impact](https://github.com/ok-oldking/ok-genshin-impact)
* Girls' Frontline 2 [https://github.com/ok-oldking/ok-gf2](https://github.com/ok-oldking/ok-gf2)
* Star Rail [https://github.com/Shasnow/ok-starrailassistant](https://github.com/Shasnow/ok-starrailassistant)
* Star Resonance [https://github.com/Sanheiii/ok-star-resonance](https://github.com/Sanheiii/ok-star-resonance)
* Duet Night Abyss [https://github.com/BnanZ0/ok-duet-night-abyss](https://github.com/BnanZ0/ok-duet-night-abyss)
* Bai Jing Corridor (maintenance stopped) [https://github.com/ok-oldking/ok-baijing](https://github.com/ok-oldking/ok-baijing)

---

## 💻 Developer Zone

### Run from source (Python)

This project supports **Python 3.12 only**. Run CMD, PyCharm, or VSCode as **Administrator**.

```bash
# If your first clone did not include submodules, initialize them first
git submodule update --init --recursive

# CPU version, using OpenVINO
pip install -r requirements.txt --upgrade

# Run Release version
python main.py

# Run Debug version
python main_debug.py
```

```bash
# CUDA version, using paddle-gpu, recommended for NVIDIA 30 series and above
pip install -r requirements-dml.txt --upgrade

# Run Release version
python main_direct_ml.py

# Run Debug version
python main_direct_ml_debug.py
```

### Command-line arguments

```pwsh
# Start and automatically run the 1st task, then exit upon completion
ok-gf2.exe -t 1 -e
```

* `-t` or `--task`: Automatically run the Nth task.
* `-e` or `--exit`: Exit automatically after the task completes.

### Developer Documentation

| Document | Description |
|----------|-------------|
| [Quick Start Guide (QUICKSTART.md)](docs/dev/QUICKSTART.md) | Minimal workflow to run from source, launch the software, and create tasks |
| [Development Guide (DEVELOPMENT.md)](docs/dev/DEVELOPMENT.md) | Architecture overview, directory structure, development workflow, testing, CI/CD |
| [API Reference (API.md)](docs/dev/API.md) | Detailed API docs for BaseGfTask, Mixin, ScreenPosition, and more |
| [i18n & OCR Configuration](docs/dev/i18n_OCR配置流程.md) | Runtime locale, language JSON, OCR matching, and text-fix workflow |
| [Keyboard System](docs/dev/键盘操作体系.md) | Hotkey mapping, key binding conventions |

## ❤️ Sponsors & Acknowledgements

### Sponsors

[![Patreon](https://img.shields.io/badge/Patreon-Support-orange?style=flat-square)](https://patreon.com/ok_oldking)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?style=flat-square)](https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ)

### Acknowledgements

* [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
* [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script)

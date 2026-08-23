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
An image-recognition-based automation tool for Girls' Frontline 2: Exilium, with background mode support, developed with <a href="https://github.com/ok-oldking/ok-script">ok-script</a>.
</p>

<p><i>Operates by simulating Windows user input. No memory reading, no file modification.</i></p>


<!-- Badges -->
<div align="center">

![Platform](https://img.shields.io/badge/platform-Windows-blue)
[![GitHub release](https://img.shields.io/github/v/release/alicejump/ok-gf2)](https://github.com/alicejump/ok-gf2/releases)
[![Total downloads](https://img.shields.io/github/downloads/alicejump/ok-gf2/total)](https://github.com/alicejump/ok-gf2/releases)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/AliceJump/ok-gf2)

</div>

> Game terms in this document use the wording shown by the **Global / Steam** client, and the
> feature list reflects what the program actually ships. See [docs/glossary.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/glossary.md)
> for the full term mapping.

---

## ⚠️ Disclaimer

This software is an external assistance tool intended to automate parts of Girls' Frontline 2: Exilium. It interacts with the game by
simulating normal user interface operations and complies with relevant laws and regulations. The project aims to reduce
repetitive actions, does not break game balance or provide unfair advantages, and never modifies any game files or data.

This software is open-source and free for personal learning and communication only. Commercial or profit-oriented use is
prohibited. The development team reserves the right of final interpretation. Any issues arising from use of this
software are unrelated to the project or its developers.

**By using this software, you acknowledge that you have read, understood, and agreed to the above statement and assume
all potential risks.**

## 🚀 Quick Start

1. **Download the package**: Choose a source below and download the latest `ok-gf2` archive.
2. **Extract and run**: Extract the archive and double-click `ok-gf2.exe`. The app can update itself from then on.
3. **Configure tasks**: Set up task parameters in the software interface as needed.

## 📥 Download Sources

* **[GitHub](https://github.com/alicejump/ok-gf2/releases)**: Official release page with fast global access. (**Download the `7z` archive, not the `Source Code` archive**)
* **[Mirrorchyan](https://mirrorchyan.com/zh/projects?rid=okgf2&source=okgf2readme)**: China mirror (may require a CD-KEY purchase).
* **[Quark Drive](https://pan.quark.cn/s/a1052cec4d13)**: Free download (requires registration and the Quark Drive client).

## Runtime Requirements & Recommendations

- OS: Windows
- Game: PC version of Girls' Frontline 2: Exilium, supports native background mode
- Resolution: All 16:9 resolutions supported, minimum 1280x720
- Frame rate: 120 FPS recommended, higher is better
- Language: Simplified Chinese or English. Pick the matching client in **Settings -> Region**
- Display: Windows Auto HDR must be disabled. RTX HDR is acceptable
- Background: Your home screen background must be **dark**. A white background breaks text recognition
- Privilege: Run as Administrator recommended, and required when running from source
- Path: Prefer an install path with no non-English characters

---

## 🎮 Feature Overview

### Which client you are automating

This fork automates the **Global (Steam, English)** client. Upstream's original CN tasks are still
here, and a setting decides which set you get.

Open **Settings** and set **Region -> Game Client** to `Global` or `CN`. It defaults to `Global`, and
**the app must be restarted after changing it**, because the task list is built at startup.

Only the selected client's tasks appear in the sidebar, but both sets are always registered. That
matters for the `-t` flag - see [Command-line arguments](#command-line-arguments).

### Tasks

These are the tasks you can select and run in the app. The number in front of each one is its
index for the `-t` command-line flag (see [Command-line arguments](#command-line-arguments)).

| # | Task | What it does |
|---|---|---|
| 1 | **[One-Click Dailies](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/daily-tasks.md)** | Runs the full daily routine top to bottom. Every step below can be toggled on or off individually |
| 2 | **[Weekly](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/weekly-tasks.md)** | Runs the weekly Combat Simulations: Boss Fight, Peak Value Assessment, Expansion Drills |
| 3 | **[Auto-Clear Campaign Stages](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/campaign-clear.md)** | Clears uncleared Campaign stages left to right |
| 4 | Launch Game | Test task. Starts the game and closes it after 120 seconds |
| 5 | Test | Test task, for development only |
| 6 | Diagnosis | Thin wrapper around the ok-script framework's built-in diagnosis task |
| 7 | **[Global Daily](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)** | Global: starts the in-game Loop, then picks up what Loop does not cover |
| 8 | **[Global Weekly](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)** | Global: collects the Peak Value Assessment rewards |
| 9 | Run: Go Home | Global: recognises the home screen, leaves it and comes back. Changes nothing |
| 10 | Run: Start Loop | Global: runs only the Start Loop step |
| 11 | Run: Claim Free Packs | Global: runs only the free shop pack step |
| 12 | Run: Event Supply | Global: runs only the event Supply step |
| 13 | Run: Claim Boundary Push | Global: runs only the Boundary Push collection |
| 14 | Run: Claim Peak Value | Global: runs only the Peak Value collection |
| 15 | Run: Crew Deck | Global: runs only the Crew Deck activities |

Tasks 1-6 are the CN set and 7-15 the Global set. The `Run: ` tasks each run a single step of Global
Daily or Global Weekly, for checking one flow at a time - see
**[docs/en/global-tasks.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)**.

### What One-Click Dailies covers

Each of these is a switch inside the Dailies task rather than a task of its own. Full details are in
**[docs/en/daily-tasks.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/daily-tasks.md)**.

- Community daily check-in (needs your username and password)
- Mail collection
- Event reward track and event stage rewards
- Auto-running the Event **Supply** stage
- **Crew Deck** activities: Tea Time, Delicious Cuisine, and reward pickup
- **Dispatch Room** assignments, dispatched and collected
- Claiming free packs from the **Shop**
- **Wishlist** purchases across Furniture Shop, Platoon Shop, Dispatch Shop, Battlelog Trading, Neural Integration, and Growth Stack
- Farming **Supply Missions** with Intelligence Puzzle
- **Combat Exercises**
- **Platoon** tasks and **Gunsmoke Frontline**
- Claiming **Commissions** rewards
- Claiming daily **Voyage** rewards
- Claiming **Boundary Push** gathering and dispatch rewards

### Scheduled tasks

Any task above can be added to the Windows Task Scheduler from inside the app, so it launches and
runs on its own at a time you set.

### Automatic in-battle behavior

Combat handling is built into the tasks above rather than being something you start separately.
While a task is running it detects the battle state and fires skills in order, picks up drops, and
skips story dialogue on its own. The program captures the game window in the background, so you can
keep using your computer while it works.

### Under the hood

- OCR text recognition, template matching, and HSV color detection
- Windows UI automation and simulated key input
- Logging, error handling, and task scheduling

---

## ⚙️ Parameter notes

### 1. Current Supply stage name (CN only)

Every Event has a **Supply** stage, which is the one that costs Intelligence Puzzle.

- In a **small event**, that stage is simply labelled **Supply**. Leave this field empty.
- In a **large event**, the stage is renamed after the event and split into parts. Enter the event
  name **without** the part suffix. For a stage shown as `铸碑者的黎明·上篇`, you would enter
  `铸碑者的黎明`.

> ⚠️ Filling this in incorrectly will break the event automation.

The Global Event Supply flow has no equivalent setting. It finds the last Supply stage on the map
by itself, and stops before spending anything if there are no event tickets left.

![image](https://github.com/user-attachments/assets/ed261840-449a-46d4-8a07-f58382f3a779)

---

### 2. Confirm the in-game global auto-battle setting is enabled

Path: **Settings -> Other -> Auto-Battle Settings**

---

### 3. Tea Time

The Crew Deck is a walkable area, so this setting is how long to hold each movement key while walking
your character over to the coffee machine. Both clients hold `A`, then `W`, then `D`.

Format: `{seconds holding A}-{seconds holding W}-{seconds holding D}`

| Client | Setting | Default |
|---|---|---|
| Global | `Tea Time Walk`, under the `Crew Deck` toggle | `0.636-1.25-0.495` |
| CN | `喝水` | `1.44-1.56-1.38` |

The right timings depend on where your character spawns, so measure your own rather than trusting the
default: run [tools/record_walk.py](https://github.com/steve1316/ok-gf2-english/blob/master/tools/record_walk.py), walk the route by hand, press Esc, and
paste the line it prints into the setting it names.

---

### 4. Delicious Cuisine

The same idea, walking to the kitchen instead. **The two clients take different routes.**

| Client | Setting | Keys | Default |
|---|---|---|---|
| Global | `Delicious Cuisine Walk`, under the `Crew Deck` toggle | holds `S` | `0.747` |
| CN | `吃饭` | holds `S`, then taps `D` | `1.3` |

Format: `{seconds holding S}`

> On Global the `Crew Deck` flow ships **switched off**, because it needs walk timings that suit your
> setup. Measure them, then turn it on.

---

![image](https://github.com/user-attachments/assets/6bd2ac34-fd40-4c74-9e8e-a0343818876d)

![image](https://github.com/user-attachments/assets/ae1ecd07-6608-478d-9226-40d4f8000a60)

---

## 🔧 Troubleshooting

If you encounter issues, check the following in order:

1. **Install path**: Install under a path with no non-English characters.
2. **Antivirus**: Add the install directory to your antivirus allow-list, including Windows Defender.
3. **Display settings**:
   * Disable Windows Auto HDR. This is required. RTX HDR is acceptable.
   * Use the game's default brightness settings.
   * Use a **dark** home screen background.
4. **Game frame rate**: 120 FPS recommended, higher is better.
5. **Game language**: Set **Settings -> Region -> Game Client** to match the client you are running, then restart the app.
6. **Software version**: Make sure you are running the latest release.
7. **Get help**: If none of the above helps, submit a detailed error report via the QQ group.

## 💬 Join Us

* **QQ Group**: `1033950808` (join answer: `老王同学OK`)

This project is built on [ok-script](https://github.com/ok-oldking/ok-script), which is easy to maintain. Developers are
welcome to build their own automation projects with ok-script.

## 🔗 Projects using ok-script

* Arknights: Endfield [https://github.com/AliceJump/ok-end-field](https://github.com/AliceJump/ok-end-field)
* Wuthering Waves [https://github.com/ok-oldking/ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)
* Wuthering Waves (enhanced daily runner) [https://github.com/zzc-tongji/ok-ww-enhanced](https://github.com/zzc-tongji/ok-ww-enhanced)
* Genshin Impact (no longer maintained, background dialogue skipping still works) [https://github.com/ok-oldking/ok-genshin-impact](https://github.com/ok-oldking/ok-genshin-impact)
* Girls' Frontline 2: Exilium [https://github.com/ok-oldking/ok-gf2](https://github.com/ok-oldking/ok-gf2)
* Honkai: Star Rail [https://github.com/Shasnow/ok-starrailassistant](https://github.com/Shasnow/ok-starrailassistant)
* Star Resonance [https://github.com/Sanheiii/ok-star-resonance](https://github.com/Sanheiii/ok-star-resonance)
* Duet Night Abyss [https://github.com/BnanZ0/ok-duet-night-abyss](https://github.com/BnanZ0/ok-duet-night-abyss)
* Bai Jing Corridor (no longer maintained) [https://github.com/ok-oldking/ok-baijing](https://github.com/ok-oldking/ok-baijing)

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
# Start, automatically run task 1 (One-Click Dailies), then exit when it finishes
ok-gf2.exe -t 1 -e
```

* `-t` or `--task`: Automatically run the Nth task. The numbering is the `#` column in
  [Tasks](#tasks), so `-t 1` is One-Click Dailies, `-t 2` is Weekly, and `-t 3` is Auto-Clear
  Campaign Stages.

  > ⚠️ These numbers count **both** task sets, and they do not shift when you change region. On a
  > Global install `-t 1` still runs the CN daily, which is not what the sidebar is showing you. The
  > Global tasks are `-t 7` (Global Daily) and `-t 8` (Global Weekly). The positions are deliberately
  > held stable so existing shortcuts and scheduled tasks keep pointing at the same task.
* `-e` or `--exit`: Exit automatically after the task completes.

### Development and testing

```bash
# Run every test script under tests/ (PowerShell)
./run_tests.ps1

# Or run a single unittest
python -m unittest tests/TestMain.py
```

### Developer Documentation

| Document | Description |
|----------|-------------|
| [Quick Start Guide (QUICKSTART.md)](https://github.com/steve1316/ok-gf2-english/blob/master/docs/dev/QUICKSTART.md) | Minimal workflow to run from source, launch the software, and create tasks |
| [Development Guide (DEVELOPMENT.md)](https://github.com/steve1316/ok-gf2-english/blob/master/docs/dev/DEVELOPMENT.md) | Architecture overview, directory structure, development workflow, testing, CI/CD |
| [API Reference (API.md)](https://github.com/steve1316/ok-gf2-english/blob/master/docs/dev/API.md) | Detailed API docs for BaseGfTask, Mixin, ScreenPosition, and more |
| [i18n & OCR Configuration](https://github.com/steve1316/ok-gf2-english/blob/master/docs/dev/i18n_OCR配置流程.md) | Runtime locale, language JSON, OCR matching, and text-fix workflow |
| [Keyboard System](https://github.com/steve1316/ok-gf2-english/blob/master/docs/dev/键盘操作体系.md) | Hotkey mapping, key binding conventions |
| [Global Client Tasks](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md) | The Global task set, the `Run: ` verification tasks, and what is not covered yet |
| [Terminology Glossary](https://github.com/steve1316/ok-gf2-english/blob/master/docs/glossary.md) | Chinese to Global / Steam English term mapping, for anyone translating this project |

Note that the developer docs above are still written in Chinese. Only the user-facing guides in
[docs/en/](https://github.com/steve1316/ok-gf2-english/tree/master/docs/en/) have been translated so far.

## ❤️ Sponsors & Acknowledgements

### Sponsors

[![Afdian](https://img.shields.io/badge/Afdian-Sponsor-blue?style=flat-square)](https://afdian.com/a/AliceJump)
[![Afdian](https://img.shields.io/badge/Afdian-Sponsor-blue?style=flat-square)](https://afdian.com/a/ok-oldking)
[![Patreon](https://img.shields.io/badge/Patreon-Support-orange?style=flat-square)](https://patreon.com/ok_oldking)
[![PayPal](https://img.shields.io/badge/PayPal-Donate-blue?style=flat-square)](https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ)

### Acknowledgements

* [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
* [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script)

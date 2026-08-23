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
[![GitHub release](https://img.shields.io/github/v/release/steve1316/ok-gf2-english)](https://github.com/steve1316/ok-gf2-english/releases)

</div>

> This is a fork of [AliceJump/ok-gf2](https://github.com/AliceJump/ok-gf2) that automates the
> **Global (Steam, English)** client. Upstream's CN tasks still ship and can be switched back on, but
> this README documents the Global side only - see [Which client you are automating](#which-client-you-are-automating).
>
> Game terms use the wording shown by the Global / Steam client. See [docs/glossary.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/glossary.md)
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

1. **Download the installer**: Grab the latest Windows installer from
   **[Releases](https://github.com/steve1316/ok-gf2-english/releases)**. Do not download the `Source Code` archives - they leave out the
   packaged dependencies.
2. **Install and run**: Run the installer, then launch `ok-gf2`. The app updates itself from then on.
3. **Configure tasks**: Set task options in the app. Start with `Run: Go Home`, which changes nothing.

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

These are the Global tasks. The number in front of each one is its index for the `-t` command-line
flag (see [Command-line arguments](#command-line-arguments)).

| # | Task | What it does |
|---|---|---|
| 7 | **[Global Daily](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)** | Starts the in-game Loop, then picks up what Loop does not cover |
| 8 | **[Global Weekly](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)** | Collects the Peak Value Assessment rewards |
| 9 | Run: Go Home | Recognises the home screen, leaves it and comes back. Changes nothing |
| 10 | Run: Start Loop | Runs only the Start Loop step |
| 11 | Run: Claim Free Packs | Runs only the free shop pack step |
| 12 | Run: Event Supply | Runs only the event Supply step |
| 13 | Run: Claim Boundary Push | Runs only the Boundary Push collection |
| 14 | Run: Claim Peak Value | Runs only the Peak Value collection |
| 15 | Run: Crew Deck | Runs only the Crew Deck activities |

The numbering starts at 7 because positions 1-6 belong to upstream's CN tasks, which still ship and
are hidden unless **Region** is set to `CN`. They are documented in
[upstream's repository](https://github.com/AliceJump/ok-gf2).

The `Run: ` tasks each run a single step of Global Daily or Global Weekly, for checking one flow at a
time - see
**[docs/en/global-tasks.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/en/global-tasks.md)**.

### Scheduled tasks

Any task above can be added to the Windows Task Scheduler from inside the app, so it launches and
runs on its own at a time you set.

### Under the hood

- OCR text recognition, template matching, and HSV color detection
- Windows UI automation and simulated key input
- Logging, error handling, and task scheduling

---

## ⚙️ Parameter notes

### 1. Tea Time

The Crew Deck is a walkable area, so this setting is how long to hold each movement key while walking
your character over to the coffee machine. It holds `A`, then `W`, then `D`.

Format: `{seconds holding A}-{seconds holding W}-{seconds holding D}`

The setting is `Tea Time Walk`, nested under the `Crew Deck` toggle. It defaults to
`0.636-1.25-0.495`.

The right timings depend on where your character spawns, so measure your own rather than trusting the
default: run [tools/record_walk.py](https://github.com/steve1316/ok-gf2-english/blob/master/tools/record_walk.py), walk the route by hand, press Esc, and
paste the line it prints into the setting it names.

---

### 2. Delicious Cuisine

The same idea, walking to the kitchen instead. This route is a single key - hold `S`.

The setting is `Delicious Cuisine Walk`, nested under the `Crew Deck` toggle. It defaults to `0.747`.

Format: `{seconds holding S}`

> On Global the `Crew Deck` flow ships **switched off**, because it needs walk timings that suit your
> setup. Measure them, then turn it on.

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
5. **Game language**: Set the game to English, and leave **Settings -> Region -> Game Client** on `Global`.
6. **Software version**: Make sure you are running the latest release.
7. **Get help**: If none of the above helps, see [Getting help](#-getting-help).

## 💬 Getting help

Open an issue on [this fork](https://github.com/steve1316/ok-gf2-english/issues) for anything to do
with the Global tasks. Attach the log and, if the bot saved one, the frame from `debug_frames/`.

Issues with the CN tasks belong [upstream](https://github.com/AliceJump/ok-gf2), along with its QQ
group.

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
# Start, automatically run task 7 (Global Daily), then exit when it finishes
ok-gf2.exe -t 7 -e
```

* `-t` or `--task`: Automatically run the Nth task. The numbering is the `#` column in
  [Tasks](#tasks), so `-t 7` is Global Daily and `-t 8` is Global Weekly.

  > ⚠️ These numbers count **both** task sets, and they do not shift when you change region. `-t 1`
  > still runs upstream's CN daily even on a Global install, which is not what the sidebar is showing
  > you. The positions are held stable on purpose, so existing shortcuts and scheduled tasks keep
  > pointing at the same task.
* `-e` or `--exit`: Exit automatically after the task completes.

### Development and testing

```bash
# Run every test script under tests/ (PowerShell)
./run_tests.ps1

# Or run a single unittest
python -m unittest tests/TestMain.py
```

### Translations

UI strings live in `i18n/<locale>/LC_MESSAGES/ok.po`. The app loads only the compiled `.mo`, so
a `.po` edit does nothing until you compile it. Commit both files.

```bash
# Install the dev dependency (polib)
pip install -r requirements-dev.txt

# Compile every .po into its .mo
python scripts/compile_i18n.py

# Verify without writing, exits non-zero if any .mo is stale (this is what CI runs)
python scripts/compile_i18n.py --check
```

See [docs/glossary.md](https://github.com/steve1316/ok-gf2-english/blob/master/docs/glossary.md) for the Chinese to Global/Steam term mapping. Note that
`ocr.po` is a different thing entirely: it rewrites English game text into the Chinese tokens the
task code matches against, so never put UI strings there.

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

## ❤️ Acknowledgements

All of the original work is [AliceJump/ok-gf2](https://github.com/AliceJump/ok-gf2) and
[ok-oldking](https://github.com/ok-oldking); this fork only adds the Global client on top. If you get
value out of it, sponsor them: [Afdian](https://afdian.com/a/AliceJump),
[Afdian](https://afdian.com/a/ok-oldking), [Patreon](https://patreon.com/ok_oldking),
[PayPal](https://www.paypal.com/ncp/payment/JWQBH7JZKNGCQ).

* [ok-oldking/OnnxOCR](https://github.com/ok-oldking/OnnxOCR)
* [zhiyiYo/PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)
* [ok-oldking/ok-script](https://github.com/ok-oldking/ok-script)

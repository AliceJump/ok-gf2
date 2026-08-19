# Auto-Clear Campaign Stages

## Overview

Clears uncleared Campaign stages one at a time, working left to right. It is meant for pushing
through Campaign progress, and supports several OCR preprocessing modes to cope with the different
ways stage cards can look.

Game terms below use the wording from the Global / Steam client. See
[../glossary.md](../glossary.md) for the full mapping.

---

## Requirements

> Your resolution must be at least **1280x720**, otherwise this may not work.

---

## How it works

1. Starting from the leftmost side of the current stage page, it looks for uncleared stages.
2. It identifies them by reading the stage name with OCR, or by template-matching the uncleared marker.
3. It clicks the stage it found and enters the battle.
4. When the battle ends it returns to the stage select page and moves on to the next stage.
5. This repeats until every clearable stage on the page is done.

---

## Recognition modes

Three OCR preprocessing modes are available. Pick whichever combination suits how your stage cards
actually look.

### Plain OCR

Reads the stage name with no image preprocessing. Best when the background and stage cards contrast
clearly against white and the text is easy to read.

### Color filter 1 (strict white)

Filters out everything that is not pure white before reading. Best when the stage card text is
standard white and a busy background is interfering.

### Color filter 2 (loose white and gray)

Keeps white and light gray areas before reading. Best when the stage card text is white or light
gray, or when neither Plain OCR nor Color filter 1 can read it.

---

## Options

| Option | Default | Description |
|------|:------:|------|
| `⭐Plain OCR` | True | Read stage names with no preprocessing |
| `⭐Color filter 1` | True | Read after filtering to strict white |
| `⭐Color filter 2` | True | Read after filtering to loose white and gray |

> If you turn all three off, the program falls back to turning all three on.

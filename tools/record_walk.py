"""Times WASD key presses, so a Crew Deck walk can be measured instead of guessed.

The Crew Deck is a walkable 3D area, so the bot reaches each station by holding movement keys for fixed durations. Those durations are settings, and the only
way to get them right is to walk the route by hand and measure it. Run this, walk from the Crew Deck entrance to a station, press Esc, and paste the line it
prints into the matching setting.

Usage, from the repository root:

    python tools/record_walk.py

Reads the key state straight from Windows rather than installing a hook, so it keeps working while the game holds focus, and needs no extra package and no
administrator rights.
"""

import ctypes
import importlib
import sys
import time

import win32api

# Virtual-key codes for the keys worth watching. Movement only, plus the two that end a recording.
MOVEMENT_KEYS = {'w': 0x57, 'a': 0x41, 's': 0x53, 'd': 0x44}
VK_ESCAPE = 0x1B
VK_BACKSPACE = 0x08

# How often to sample the keyboard. 1 ms is finer than the millisecond the settings are written to, and
# `timeBeginPeriod` is what makes a sleep this short actually last that long rather than a whole tick.
POLL_SECONDS = 0.001

# Anything shorter than this is a stray brush of a key rather than a step, and is dropped.
MIN_HOLD_SECONDS = 0.03


def is_down(virtual_key):
    """Whether a key is physically held right now.

    Args:
        virtual_key: A Windows virtual-key code.

    Returns:
        True while the key is down.
    """
    return bool(win32api.GetAsyncKeyState(virtual_key) & 0x8000)


def stations():
    """Load the walk definitions from the task itself, so this tool cannot drift from the code it feeds.

    Returns:
        The `STATIONS` table from `GlobalDailyTask`, or an empty tuple when it could not be imported.
    """
    try:
        return importlib.import_module('src.global.GlobalDailyTask').STATIONS
    except Exception as error:
        print(f'(could not read the station table: {error}. Run this from the repository root for a fuller summary.)\n')
        return ()


def record():
    """Watch the keyboard until Esc, timing every movement key held along the way.

    Returns:
        A list of `(key, hold seconds, gap seconds since the previous release)` in the order the keys were pressed, or None when the recording was discarded.
    """
    held = {}
    presses = []
    last_release = None
    while True:
        now = time.perf_counter()
        if is_down(VK_ESCAPE):
            break
        if is_down(VK_BACKSPACE):
            presses.clear()
            held.clear()
            last_release = None
            print('  -- cleared, start again --')
            # Wait for the key to come back up, so one press does not clear repeatedly.
            while is_down(VK_BACKSPACE):
                time.sleep(POLL_SECONDS)
        for key, virtual_key in MOVEMENT_KEYS.items():
            down = is_down(virtual_key)
            if down and key not in held:
                held[key] = now
            elif not down and key in held:
                hold = now - held.pop(key)
                if hold < MIN_HOLD_SECONDS:
                    continue
                gap = now - hold - last_release if last_release is not None else None
                presses.append((key, hold, gap))
                spacing = f'   after a {gap:.2f}s gap' if gap is not None else ''
                print(f'  {key}   held {hold:.3f}s{spacing}')
                last_release = now
        time.sleep(POLL_SECONDS)
    # A key still held at Esc would otherwise be dropped without a word, leaving a short walk that looks
    # complete. Close it off at the moment the recording stopped instead.
    for key, pressed_at in held.items():
        hold = time.perf_counter() - pressed_at
        presses.append((key, hold, None))
        print(f'  {key}   held {hold:.3f}s, still down when the recording stopped')
    return presses


def describe(presses):
    """Print the recording as something that can be pasted into a setting.

    Args:
        presses: The `(key, hold, gap)` list from `record`.
    """
    keys = [key for key, _, _ in presses]
    setting = '-'.join(f'{hold:.3f}'.rstrip('0').rstrip('.') for _, hold, _ in presses)
    gaps = [gap for _, _, gap in presses if gap is not None]
    print(f'\nSequence: {" ".join(keys)}')
    print(f'Setting:  {setting}')
    if gaps:
        print(f'Gaps:     {", ".join(f"{gap:.2f}s" for gap in gaps)}')

    for station in stations():
        if keys == list(station.keys):
            print(f'\nPaste "{setting}" into the "{station.config_key}" setting, for {station.label}.')
            if gaps and max(abs(gap - station.sleep_between) for gap in gaps) > 0.3:
                print(f'Note: the bot pauses a fixed {station.sleep_between}s between keys, and you paused {", ".join(f"{gap:.2f}s" for gap in gaps)}.')
                print('If the walk lands short, say so and that pause can become a setting too.')
            return
    known = ' or '.join(' '.join(station.keys) for station in stations()) or 'the ones in the task'
    print(f'\nThis key sequence is not one the task knows - it walks {known}.')
    print('Send the sequence over and the station table can be changed to match.')


def main():
    """Record one walk and print it.

    Returns:
        A process exit code.
    """
    if sys.platform != 'win32':
        print('This reads the Windows keyboard state, so it only runs on Windows.')
        return 1
    # Without this a 1 ms sleep lasts a whole scheduler tick, which is coarser than the timings being measured.
    ctypes.windll.winmm.timeBeginPeriod(1)
    try:
        print('Recording. Switch to the game, walk from the Crew Deck entrance to the station, then press Esc.')
        print('Backspace clears the recording if you want to start the walk again.\n')
        presses = record()
    finally:
        ctypes.windll.winmm.timeEndPeriod(1)
    if not presses:
        print('\nNothing recorded.')
        return 1
    describe(presses)
    return 0


if __name__ == '__main__':
    sys.exit(main())

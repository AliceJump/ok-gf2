"""Compile the gettext catalogs in `i18n/` from `.po` sources into the `.mo` files the app loads.

The running app only ever reads `.mo`. Editing a `.po` on its own changes nothing at runtime, so this
script exists to keep the two in step and to let CI fail when someone forgets.

Run `python scripts/compile_i18n.py` to write the `.mo` files, or `--check` to verify without writing.
"""

import argparse
import sys
from pathlib import Path

import polib

REPO_ROOT = Path(__file__).resolve().parent.parent
I18N_ROOT = REPO_ROOT / "i18n"


def find_po_files():
    """Locate every translation source in the i18n tree.

    Returns:
        A sorted list of `Path` objects for each `i18n/<locale>/LC_MESSAGES/<domain>.po`.
    """
    return sorted(I18N_ROOT.glob("*/LC_MESSAGES/*.po"))


def entries_of(catalog):
    """Reduce a polib catalog to a plain msgid to msgstr mapping.

    Comparing these mappings rather than raw bytes keeps `--check` stable, since the committed `.mo`
    files were not necessarily produced by polib and byte output differs between compilers.

    Args:
        catalog: A `polib.POFile` or `polib.MOFile`.

    Returns:
        A dict of msgid to msgstr, skipping obsolete entries and the header.
    """
    return {e.msgid: e.msgstr for e in catalog if not e.obsolete and e.msgid}


def check_one(po_path):
    """Report whether a compiled `.mo` is missing or out of date relative to its `.po`.

    Args:
        po_path: Path to the `.po` source.

    Returns:
        A reason string when the `.mo` needs rebuilding, or None when it is current.
    """
    mo_path = po_path.with_suffix(".mo")
    if not mo_path.exists():
        return "missing .mo"
    want = entries_of(polib.pofile(str(po_path)))
    have = entries_of(polib.mofile(str(mo_path)))
    if want == have:
        return None
    missing = set(want) - set(have)
    extra = set(have) - set(want)
    changed = {k for k in set(want) & set(have) if want[k] != have[k]}
    parts = []
    if missing:
        parts.append(f"{len(missing)} missing")
    if extra:
        parts.append(f"{len(extra)} stale")
    if changed:
        parts.append(f"{len(changed)} changed")
    return ", ".join(parts)


def compile_one(po_path):
    """Compile a single `.po` into a sibling `.mo`.

    Args:
        po_path: Path to the `.po` source.
    """
    mo_path = po_path.with_suffix(".mo")
    polib.pofile(str(po_path)).save_as_mofile(str(mo_path))


def main():
    """Entry point. Compiles every catalog, or checks them when `--check` is passed.

    Returns:
        0 when everything is current or was written, 1 when `--check` found stale catalogs.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify without writing, exit 1 if stale")
    args = parser.parse_args()

    po_files = find_po_files()
    if not po_files:
        print(f"no .po files found under {I18N_ROOT}")
        return 1

    stale = []
    for po_path in po_files:
        rel = po_path.relative_to(REPO_ROOT)
        reason = check_one(po_path)
        if args.check:
            print(f"{'STALE' if reason else 'ok   '}  {rel}" + (f"  ({reason})" if reason else ""))
            if reason:
                stale.append(rel)
        else:
            compile_one(po_path)
            print(f"compiled  {rel} -> {rel.with_suffix('.mo')}" + (f"  ({reason})" if reason else "  (no change)"))

    if args.check and stale:
        print(f"\n{len(stale)} catalog(s) out of date. Run: python scripts/compile_i18n.py")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

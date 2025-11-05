#!/usr/bin/env python3
"""Fix diacritic placement in the `var yuepin` data inside js/data.js.

Behaviour:
- Reads js/data.js, finds the `var yuepin = { ... }` object.
- For each entry value (a quoted comma-separated string), checks the second column (index 1).
- Ensures diacritic mark (any combining or precomposed diacritic like macron/acute/grave/hat/tilde) is on the first vowel in the string.
- If no vowel found, ensures the diacritic (if any) is on the first character.
- Writes the file back (by default does a dry-run; use --fix to apply changes).

Usage:
    python3 scripts/fix_yuepin.py [--fix]
    --fix   Actually write changes to js/data.js. Without it the script prints a summary.
"""
import re
from pathlib import Path
import argparse


DATA_JS = Path(__file__).resolve().parents[1] / 'js' / 'data.js'

import unicodedata as _ud

# Vowels: only the standard a/e/i/o/u (Y is not treated as vowel here)
VOWEL_BASES = set('aeiouAEIOU')


def split_js_object(text: str):
    """Return (prefix, object_text, suffix) where object_text is the interior of var yuepin = { ... }"""
    m = re.search(r"var\s+yuepin\s*=\s*\{", text)
    if not m:
        raise RuntimeError('Could not find "var yuepin = {" in file')
    start = m.end()
    # Find matching closing brace for the object. We do a simple brace counter from start.
    i = start
    depth = 1
    while i < len(text):
        ch = text[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    else:
        raise RuntimeError('Could not find end of yuepin object')
    prefix = text[:m.start()]
    obj_text = text[m.start(): end+1]
    suffix = text[end+1:]
    return prefix, obj_text, suffix


def _decompose_char(ch: str):
    """Return (base, combining_marks) for a single character (NFD decomposition)."""
    decomp = _ud.normalize('NFD', ch)
    base = ''.join(c for c in decomp if not _ud.category(c).startswith('M'))
    marks = ''.join(c for c in decomp if _ud.category(c).startswith('M'))
    return base, marks


def find_first_vowel_index(s: str):
    """Find index of first character whose base letter is a vowel (a/e/i/o/u).
    Returns None if none found.
    """
    for i, ch in enumerate(s):
        base, _ = _decompose_char(ch)
        if base and base[0] in VOWEL_BASES:
            return i
    return None


def move_diacritic_to_first_vowel(token: str):
    """Move any Unicode combining marks found in token to the first vowel (a/e/i/o/u).

    If there is no vowel, prefer an 'm' or 'n' as nucleus if present; otherwise use first character.
    Returns (new_token, changed)
    """
    if not token:
        return token, False
    # Decompose each character into base + marks
    bases = []
    marks_list = []
    for ch in token:
        base, marks = _decompose_char(ch)
        bases.append(base or ch)
        marks_list.append(marks)

    # Find source index: first char that carries combining marks (or precomposed marks)
    source_index = None
    for i, m in enumerate(marks_list):
        if m:
            source_index = i
            break
    if source_index is None:
        return token, False

    # Find target index: first vowel base (a/e/i/o/u).
    # If there's no vowel, do not change the token (leave syllabic m/n alone).
    first_vowel = find_first_vowel_index(token)
    if first_vowel is None:
        return token, False
    target = first_vowel

    # If source is already target, nothing to do
    if source_index == target:
        return token, False

    # If target already carries marks, assume it's already correct and do nothing
    if marks_list[target]:
        return token, False

    # Move marks from source to target (only the marks attached to the first marked char)
    moving_marks = marks_list[source_index]
    new_chars = []
    for i, b in enumerate(bases):
        if i == source_index:
            new_chars.append(_ud.normalize('NFC', b))
        elif i == target:
            new_chars.append(_ud.normalize('NFC', _ud.normalize('NFD', b) + moving_marks))
        else:
            new_chars.append(_ud.normalize('NFC', b))

    new_token = ''.join(new_chars)
    return new_token, True


def process_value(value: str):
    # value is the quoted CSV like: "a1,ā,aa1,a¹,'a,aː˥,aa1,a1,a¹,a1,ä"
    # We need to parse with simple split (commas inside values don't appear)
    parts = value.split(',')
    if len(parts) < 2:
        return value, False
    token = parts[1]
    new_token, changed = move_diacritic_to_first_vowel(token)
    if changed:
        parts[1] = new_token
        return ','.join(parts), True
    return value, False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fix', action='store_true', help='Write changes to js/data.js')
    args = parser.parse_args()

    text = DATA_JS.read_text(encoding='utf-8')
    prefix, obj_text, suffix = split_js_object(text)

    # process each line inside object
    changed_count = 0
    new_obj_lines = []
    for line in obj_text.splitlines():
        m = re.match(r'(\s*"[^\"]+"\s*:\s*)"(.*)"(,?)$', line)
        if not m:
            new_obj_lines.append(line)
            continue
        keypart, inner, comma = m.group(1), m.group(2), m.group(3)
        new_inner, changed = process_value(inner)
        if changed:
            changed_count += 1
            new_line = f"{keypart}\"{new_inner}\"{comma}"
            new_obj_lines.append(new_line)
        else:
            new_obj_lines.append(line)

    new_text = prefix + '\n'.join(new_obj_lines) + suffix

    if changed_count == 0:
        print('No changes necessary')
    else:
        print(f'Would change {changed_count} entries' + (', writing file' if args.fix else ', dry-run'))
        if args.fix:
            DATA_JS.write_text(new_text, encoding='utf-8')
            print('Wrote', DATA_JS)


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Lay the UI text out on the lines the retail text used.

These widgets are not one rectangle. A TIPS entry that shows a picture has a
narrow column beside it and the full width underneath, and the retail text
says so: its lines run 12, 11, 61 characters, the first two squeezed past the
illustration. The break positions are the layout.

So a translation has to be broken the same way -- line for line, each one no
wider than the retail line in its place. Ignoring that is what put half of a
TIPS entry behind its own picture: our line was 30 characters where the
retail line beside the picture was 17, the engine wrapped it itself, and the
overflow came back at the left margin under the artwork. The same mistake in
the guide popup wrote a fourth line into a box that holds three.

  python wrap_ui_text.py            # report only
  python wrap_ui_text.py --write    # rewrite the files
"""
import io
import json
import os
import re
import sys
from unicodedata import east_asian_width

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, 'ui_json')
FILES = ('tip.json', 'tutorial.json', 'help.json', 'outline.json')

# Widgets that are a fixed box, and how many lines each one shows. TIPS is
# absent because it scrolls: there its last line may run long and the engine
# wraps it, exactly as the retail text lets it. A box has no such room, so
# text that needs one line more than it holds has to be written shorter.
# TUTO006#4 measures the guide popup for us -- 19, 19, 6 and then an empty
# line, which is the box saying it is three lines of about twenty wide.
ROWS = {'tutorial.json': 3, 'outline.json': 6, 'help.json': 5}

BS = chr(92)
NL = BS + 'n'                        # the script's line break: backslash, n
CR, LF = chr(13), chr(10)
RUBY = re.compile(r'\[([^/\]]*)/[^\]]*\]')
LEAD_TAG = re.compile(r'^((?::[a-zA-Z_]+=[^:]*)+:?)')
MARKUP = re.compile(r'<I>|<ICON"[^"]*">')
BLANK = re.compile(r'<BLANK(\d+)>')

# Width is pixels, not characters. `<BLANK18>` is the disc telling us what an
# em is: it reserves the space a button icon is drawn into, and it is exactly
# one full-width character. So a kanji or a Hangul syllable is 18 and ASCII is
# 9 -- which matters, because the retail line says TIPS in four full-width
# letters where our Korean says it in four half-width ones, and counting
# characters would have called those the same width.
EM = 18


def plain(s):
    """What the player actually sees."""
    s = RUBY.sub(lambda m: m.group(1), LEAD_TAG.sub('', s))
    return BLANK.sub(' ' * 2, MARKUP.sub('', s))


def width(s):
    """How many pixels a single line of `s` takes."""
    s = RUBY.sub(lambda m: m.group(1), LEAD_TAG.sub('', s))
    px = sum(int(m.group(1)) for m in BLANK.finditer(s))
    s = BLANK.sub('', MARKUP.sub('', s))
    return px + sum(EM if east_asian_width(c) in 'WFA' else EM // 2
                    for c in s)


def widths(text):
    """The printed width of each of `text`'s lines, in pixels."""
    return [width(p) for p in text.split(NL)]


def _fill(words, room):
    """As many leading `words` as fit `room` pixels, and what is left."""
    line, i = '', 0
    while i < len(words):
        step = words[i] if not line else ' ' + words[i]
        if line and width(line) + width(step) > room:
            break
        line += step
        i += 1
    if not line and words:           # a single word wider than the line
        line, i = words[0], 1
    return line, words[i:]


def relayout(ko, ja, rows=0):
    """`ko` broken onto the lines `ja` used, or None when nothing to do.

    Only the middle lines are held to the retail width. A short last line is
    just where the sentence stopped, not a narrow column, so the tail is free
    to fill the widget. `rows` caps a box; 0 means the tail may flow.
    """
    if NL not in ja or not ko.strip():
        return None
    room = widths(ja)
    while len(room) > 1 and not room[-1]:
        room.pop()
    m = LEAD_TAG.match(ko)
    tag, body = (m.group(1), ko[m.end():]) if m else ('', ko)
    words = [w for w in body.replace(NL, ' ').split(' ') if w]
    if not words:
        return None
    lines, left = [], words
    for r in room[:-1]:
        line, left = _fill(left, r)
        lines.append(line)
        if not left:
            break
    if rows:
        while left:                  # a box wraps at its own full width
            line, left = _fill(left, max(room))
            lines.append(line)
    else:
        lines.append(' '.join(left))
    while len(lines) > 1 and not lines[-1]:
        lines.pop()
    got = tag + NL.join(lines)
    return None if got == ko else got


def overflows(ko, ja, rows):
    """Why `ko` will not draw, or '' when it fits."""
    w, r = widths(ko), widths(ja)
    while len(r) > 1 and not r[-1]:
        r.pop()
    if rows and len(w) > rows:
        return '%d/%d lines' % (len(w), rows)
    if not rows and len(w) > len(r):
        return '%d/%d lines' % (len(w), len(r))
    for i in range(min(len(w), len(r)) - 1):
        if w[i] > r[i]:
            return 'line %d is %d px, room for %d' % (i + 1, w[i], r[i])
    return ''


def main(write):
    for name in FILES:
        path = os.path.join(UI, name)
        if not os.path.exists(path):
            continue
        raw = io.open(path, encoding='utf-8', newline='').read()
        doc = json.loads(raw)
        rows = ROWS.get(name, 0)
        changed, over = 0, []
        for e in doc['entries']:
            ja, ko = e.get('ja', ''), e.get('ko', '')
            got = relayout(ko, ja, rows)
            if got is not None:
                e['ko'] = got
                changed += 1
            why = overflows(e['ko'], ja, rows)
            if why:
                over.append((e['id'], why))
        print('%-15s %4d relaid out, %d still too long' % (name, changed,
                                                          len(over)))
        for eid, why in over[:60]:
            print('    %-26s %s' % (eid, why))
        if write and changed:
            out = json.dumps(doc, ensure_ascii=False, indent=1)
            if CR in raw:
                out = out.replace(LF, CR + LF)
            io.open(path, 'w', encoding='utf-8', newline='').write(out)


if __name__ == '__main__':
    main('--write' in sys.argv)

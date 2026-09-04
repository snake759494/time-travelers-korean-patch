# -*- coding: utf-8 -*-
"""Put the line breaks back into UI text that lost them in translation.

The retail strings carry explicit breaks. Several translation files dropped
them, and without a break the game wraps by itself -- and its own wrap eats
the first character of every line it makes, which is what the TIPS entries
looked like on hardware.

Each entry is wrapped to the width its own Japanese used, measured with the
ruby brackets and any `:texture=`/`:pos=` control run taken out, since neither
occupies screen width. A leading control run stays glued to the first line.

  python wrap_ui_text.py            # report only
  python wrap_ui_text.py --write    # rewrite the files
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UI = os.path.join(ROOT, 'ui_json')
FILES = ('tip.json', 'tutorial.json', 'help.json', 'outline.json')

BS = chr(92)
NL = BS + 'n'
RUBY = re.compile(r'\[([^/\]]*)/[^\]]*\]')
LEAD_TAG = re.compile(r'^((?::[a-zA-Z_]+=[^:]*)+:?)')


def plain(s):
    """What the player actually sees, for measuring width."""
    return RUBY.sub(lambda m: m.group(1), LEAD_TAG.sub('', s))


def width_of(ja):
    """The widest printed line the Japanese used."""
    return max((len(plain(p)) for p in ja.split(NL) if p.strip()), default=0)


def wrap(text, width):
    out, cur = [], ''
    for word in text.split(' '):
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= width:
            cur += ' ' + word
        else:
            out.append(cur)
            cur = word
    if cur:
        out.append(cur)
    return out


def fix(ko, ja, limit=None):
    """`ko` broken to the width `ja` used, or None when nothing to do.

    The test is the width of the widest line, not whether the breaks are
    there at all: an entry that kept some of its breaks but not all still
    has one line running past the edge, and the engine's own wrap is what
    eats a character.
    """
    if NL not in ja or not ko.strip():
        return None
    width = width_of(ja)
    # The ceiling is the widget's, not this entry's: the outline box holds
    # 20 characters because other summaries in the same file use 20, and
    # rewrapping a 20-wide line to a 19-wide neighbour only costs a line.
    if width < 4 or width_of(ko) <= max(width, limit or 0):
        return None
    m = LEAD_TAG.match(ko)
    tag, body = (m.group(1), ko[m.end():]) if m else ('', ko)
    lines = wrap(body.replace(NL, ' '), width)
    if len(lines) < 2:
        return None
    return tag + NL.join(lines)


def main(write):
    for name in FILES:
        path = os.path.join(UI, name)
        if not os.path.exists(path):
            continue
        raw = open(path, encoding='utf-8', newline='').read()
        doc = json.loads(raw)
        crlf = '\r\n' in raw
        changed = over = 0
        limit = max((width_of(e.get('ja', '')) for e in doc['entries']),
                    default=0)
        rows = max((e.get('ja', '').count(NL) for e in doc['entries']),
                   default=0)
        tall = [e['id'] for e in doc['entries']
                if e.get('ko', '').count(NL) > rows]
        for e in doc['entries']:
            got = fix(e.get('ko', ''), e.get('ja', ''), limit)
            if got is None:
                continue
            if got.count(NL) > e['ja'].count(NL):
                over += 1
            e['ko'] = got
            changed += 1
        print('%-15s %4d entries rewrapped, %d longer than the original;'
              ' %d run past the %d lines the retail text uses%s'
              % (name, changed, over, len(tall), rows + 1,
                 ': ' + ', '.join(tall[:6]) if tall else ''))
        if write and changed:
            out = json.dumps(doc, ensure_ascii=False, indent=1)
            if crlf:
                out = out.replace('\n', '\r\n')
            open(path, 'w', encoding='utf-8', newline='').write(out)


if __name__ == '__main__':
    main('--write' in sys.argv)

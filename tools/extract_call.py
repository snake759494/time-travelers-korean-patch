# -*- coding: utf-8 -*-
"""Pull the phone conversations out into a translation file.

  python extract_call.py            # writes ui_json/call.json

The lines live in psp/ttp/call/*.bin inside TTP.cpk (see ttpcall). Entries are
keyed by file and string offset, which is what patch_call reads back, and the
same words recur across calls -- 6131 strings are 3016 distinct ones -- so the
file is written with one entry per distinct string and a `where` list saying
where it goes. Translating a line once therefore translates every call that
uses it.

`ko` starts empty; whatever is filled in gets written into the build and the
rest stays Japanese, so the file can be translated a piece at a time. An
existing call.json is never overwritten -- its `ko` values are carried across
and only new strings are added.
"""
import io
import json
import os
import re

import cpk
import dnsfile
import ttpcall

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'ui_json', 'call.json')
ENC = 'cp932'
JP = re.compile(r'[぀-ヿ一-鿿]')


def calls(d=None):
    """[(cpk entry, Call)] for every phone file we can read."""
    c = cpk.CPK(d or dnsfile.DNSFile())
    ttp = [x for x in c.files if x['name'] == 'TTP.cpk'][0]
    inner = cpk.CPK(io.BytesIO(c.read(ttp)))
    out = []
    for e in sorted((x for x in inner.files
                     if x['dir'] == 'psp/ttp/call' and x['name'].endswith('.bin')),
                    key=lambda x: x['name']):
        t = ttpcall.parse(inner.read(e))
        if t is not None:
            out.append((e, t))
    return inner, out


def main():
    _, got = calls()
    old = {}
    if os.path.exists(OUT):
        for e in json.load(open(OUT, encoding='utf-8'))['entries']:
            if e.get('ko', '').strip():
                old[e['ja']] = e['ko']
    seen, entries = {}, []
    for e, t in got:
        for off, raw in t.strings():
            try:
                ja = raw.decode(ENC)
            except UnicodeDecodeError:
                continue
            if not JP.search(ja):
                continue
            where = '%s@%d' % (e['name'], off)
            if ja in seen:
                seen[ja]['where'].append(where)
                continue
            item = {'id': where, 'ja': ja, 'ko': old.get(ja, ''), 'where': [where]}
            seen[ja] = item
            entries.append(item)
    doc = {
        'schema': 'tt1-call/1',
        'source': 'TTP.cpk psp/ttp/call/*.bin',
        'note': 'phone conversations; a line is stored once and listed in '
                '`where` for every call that uses it. \\n is a real newline '
                'here, not the two characters the event script uses.',
        'count': len(entries),
        'places': sum(len(x['where']) for x in entries),
        'entries': entries,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1).replace('\n', '\r\n'))
    done = sum(1 for x in entries if x['ko'].strip())
    print('%s: %d distinct strings in %d places, %d already translated'
          % (OUT, len(entries), doc['places'], done))


if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
"""Pull the TTP_* tables out into a translation file, in the project's format.

  python extract_table.py            # writes ui_json/table.json

Each entry is keyed by file and string offset, which is what patch_table reads
back. `ko` starts empty; whatever is filled in gets written into the build, and
entries left empty stay Japanese, so the file can be translated a piece at a
time. An existing table.json is never overwritten -- its `ko` values are
carried across and only new strings are added.
"""
import io
import json
import os
import re
import sys

import cpk
import dnsfile
import ttptable

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'ui_json', 'table.json')
ENC = 'cp932'
JP = re.compile(r'[぀-ヿ一-鿿]')
FILES = ('mail.bin', 'diary.bin', 'tips.bin', 'event.bin')


def tables(d=None):
    """{name: (cpk entry, Table)} for every TTP_* table we can parse."""
    c = cpk.CPK(d or dnsfile.DNSFile())
    ttp = [x for x in c.files if x['name'] == 'TTP.cpk'][0]
    inner = cpk.CPK(io.BytesIO(c.read(ttp)))
    out = {}
    for name in FILES:
        e = [x for x in inner.files if x['name'] == name]
        if not e:
            continue
        t = ttptable.parse(inner.read(e[0]))
        if t is not None:
            out[name] = (e[0], t)
    return inner, out


def main():
    _, got = tables()
    old = {}
    if os.path.exists(OUT):
        for e in json.load(open(OUT, encoding='utf-8'))['entries']:
            if e.get('ko', '').strip():
                old[e['id']] = e['ko']
    entries = []
    for name in FILES:
        if name not in got:
            continue
        _, t = got[name]
        for off, raw in t.strings():
            try:
                ja = raw.decode(ENC)
            except UnicodeDecodeError:
                continue
            if not JP.search(ja):
                continue
            key = '%s@%d' % (name, off)
            entries.append({'id': key, 'ja': ja, 'ko': old.get(key, '')})
    doc = {
        'schema': 'tt1-table/1',
        'source': 'TTP.cpk psp/ttp/table/*.bin',
        'note': 'mail, diary and TIPS tables; strings are appended and the '
                'offset slots repointed, so a translation may be any length',
        'count': len(entries),
        'entries': entries,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8', newline='') as fh:
        fh.write(json.dumps(doc, ensure_ascii=False, indent=1).replace('\n', '\r\n'))
    done = sum(1 for e in entries if e['ko'].strip())
    print('%s: %d strings, %d already translated' % (OUT, len(entries), done))


if __name__ == '__main__':
    main()

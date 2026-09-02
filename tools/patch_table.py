# -*- coding: utf-8 -*-
"""Write ui_json/table.json back into the TTP_* tables inside TTP.cpk.

TTP.cpk is stored plain inside the install stream, and each table sits in its
own slot inside it, so an edit is just bytes at an absolute offset -- the same
shape the chapter archives use. Translated strings are appended to the table
and their offset slots repointed (see ttptable), then the table is compressed
back into the slot it already had.

Entries whose `ko` is empty are left alone, so the file can be translated a
piece at a time.
"""
import io
import json
import os
import struct

import cpk
import crilayla
import ttptable

ENC = 'cp932'


def patch(c, d, table, ui_dir, recode, fit):
    """[(absolute offset, bytes)] for the tables, plus a count and skips."""
    path = os.path.join(ui_dir, 'table.json')
    if not os.path.exists(path):
        return [], 0, ['no table.json']
    want = {}
    for e in json.load(open(path, encoding='utf-8'))['entries']:
        if e.get('ko', '').strip():
            want[e['id']] = e['ko']
    if not want:
        return [], 0, []

    ttp = [x for x in c.files if x['name'] == 'TTP.cpk'][0]
    blob = c.read(ttp)
    inner = cpk.CPK(io.BytesIO(blob))
    itoc = cpk.read_chunk(inner.f, inner.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(itoc.rows)}
    ibase = inner.header['TocOffset'] + 24 + itoc.rows_off

    edits, done, skipped = [], 0, []
    for name in ('mail.bin', 'diary.bin', 'tips.bin', 'event.bin'):
        hits = {k: v for k, v in want.items() if k.startswith(name + '@')}
        if not hits:
            continue
        e = [x for x in inner.files if x['name'] == name]
        if not e:
            continue
        e = e[0]
        t = ttptable.parse(inner.read(e))
        if t is None:
            skipped.append((name, 'unreadable'))
            continue
        replace = {}
        for key, ko in hits.items():
            off = int(key.split('@')[1])
            try:
                replace[off] = recode(ko, table)
            except UnicodeEncodeError:
                continue
        if not replace:
            continue
        raw = t.pack(replace)
        nxt = min(x['offset'] for x in inner.files if x['offset'] > e['offset'])
        slot = nxt - e['offset']
        comp = fit(raw, slot) if e['size'] != e['extract'] else raw
        if len(comp) > slot:
            skipped.append((name, len(comp), slot))
            continue
        # absolute: where TTP.cpk sits, plus where the table sits inside it
        edits.append((ttp['offset'] + e['offset'], comp))
        row = ibase + row_of[(e['dir'], e['name'])] * itoc.row_len
        edits.append((ttp['offset'] + row + 8, struct.pack('>I', len(comp))))
        edits.append((ttp['offset'] + row + 12, struct.pack('>I', len(raw))))
        done += len(replace)
    return edits, done, skipped

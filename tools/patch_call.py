# -*- coding: utf-8 -*-
"""Write ui_json/call.json back into psp/ttp/call/*.bin inside TTP.cpk.

TTP.cpk is stored plain inside the install stream, so an edit is bytes at an
absolute offset -- the same shape patch_table uses for the mail and TIPS
tables. Each phone file keeps its own length: a translated line is written
where the Japanese was whenever it fits, which it nearly always does because
the Japanese carries ruby the Korean does not (see ttpcall.pack).

Entries whose `ko` is empty are left alone, so the file can be translated a
piece at a time, and a file that would outgrow its slot is skipped whole
rather than moved.
"""
import io
import json
import os
import struct

import cpk
import ttpcall

ENC = 'cp932'
DIR = 'psp/ttp/call'


def patch(c, d, table, ui_dir, recode, fit):
    """[(absolute offset, bytes)] for the phone files, plus a count and skips."""
    path = os.path.join(ui_dir, 'call.json')
    if not os.path.exists(path):
        return [], 0, ['no call.json']
    want = {}
    for e in json.load(open(path, encoding='utf-8'))['entries']:
        if not e.get('ko', '').strip():
            continue
        for where in e.get('where') or [e['id']]:
            name, off = where.split('@')
            want.setdefault(name, {})[int(off)] = e['ko']
    if not want:
        return [], 0, []

    ttp = [x for x in c.files if x['name'] == 'TTP.cpk'][0]
    blob = c.read(ttp)
    inner = cpk.CPK(io.BytesIO(blob))
    itoc = cpk.read_chunk(inner.f, inner.header['TocOffset'], b'TOC ')
    row_of = {(r['DirName'], r['FileName']): i for i, r in enumerate(itoc.rows)}
    ibase = inner.header['TocOffset'] + 24 + itoc.rows_off
    order = sorted(inner.files, key=lambda x: x['offset'])
    after = {a['offset']: b['offset'] for a, b in zip(order, order[1:])}
    after[order[-1]['offset']] = len(blob)

    edits, done, skipped = [], 0, []
    for e in sorted((x for x in inner.files if x['dir'] == DIR),
                    key=lambda x: x['name']):
        hits = want.get(e['name'])
        if not hits:
            continue
        t = ttpcall.parse(inner.read(e))
        if t is None:
            skipped.append((e['name'], 'unreadable'))
            continue
        known = {off for off, _ in t.strings()}
        replace = {}
        for off, ko in hits.items():
            if off not in known:
                continue
            try:
                replace[off] = recode(ko, table)
            except UnicodeEncodeError:
                continue
        if not replace:
            continue
        raw = t.pack(replace)
        slot = after[e['offset']] - e['offset']
        comp = fit(raw, slot) if e['size'] != e['extract'] else raw
        if len(comp) > slot:
            skipped.append((e['name'], len(comp), slot))
            continue
        # absolute: where TTP.cpk sits, plus where the file sits inside it
        edits.append((ttp['offset'] + e['offset'], comp))
        row = ibase + row_of[(e['dir'], e['name'])] * itoc.row_len
        edits.append((ttp['offset'] + row + 8, struct.pack('>I', len(comp))))
        edits.append((ttp['offset'] + row + 12, struct.pack('>I', len(raw))))
        done += len(replace)
    return edits, done, skipped
